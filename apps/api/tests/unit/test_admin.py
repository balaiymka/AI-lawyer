"""Админка без БД: пароли, токены, права доступа, фоновые задачи."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import get_settings
from app.db.models.users import User, UserRole
from app.main import app
from app.services.admin import jobs


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "test-secret-value-for-unit-tests-0123456789")


def make_user(role: UserRole) -> User:
    return User(id=uuid.uuid4(), email=f"{role.value}@test.kz", role=role)


def test_password_hash_roundtrip():
    h = security.hash_password("very-secret-1")
    assert h.startswith("scrypt$") and "very-secret-1" not in h
    assert security.verify_password("very-secret-1", h)
    assert not security.verify_password("wrong", h)
    assert not security.verify_password("x", None)


def test_admin_endpoints_need_login():
    client = TestClient(app)
    assert client.get("/v1/admin/acts").status_code == 401
    assert client.get("/v1/admin/acts", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_roles_are_enforced(monkeypatch):
    client = TestClient(app)
    lawyer = make_user(UserRole.lawyer)
    app.dependency_overrides[security.current_user] = lambda: lawyer
    try:
        assert client.get("/v1/admin/jobs").status_code == 200          # юрист видит задачи
        assert client.get("/v1/admin/users").status_code == 403         # но не сотрудников
        assert client.post("/v1/admin/acts/ZHO/reindex").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_token_carries_user_and_role():
    import jwt

    u = make_user(UserRole.admin)
    tok = security.issue_token(u)
    data = jwt.decode(tok, get_settings().jwt_secret, algorithms=["HS256"])
    assert data["sub"] == str(u.id) and data["role"] == "admin"


def _wait(job, timeout=5):
    t = time.time()
    while job.status in ("queued", "running") and time.time() - t < timeout:
        time.sleep(0.02)
    return job


def test_jobs_run_sync_async_and_report_errors():
    ok = _wait(jobs.submit("t", "sync", lambda log: (log("шаг"), 42)[1], act_code="X1"))
    assert ok.status == "done" and ok.result == 42 and any("шаг" in line for line in ok.log)

    async def coro(log):
        log("async")
        return {"n": 1}

    a = _wait(jobs.submit("t", "async", coro))
    assert a.status == "done" and a.result == {"n": 1}

    def boom(log):
        raise ValueError("на эту дату акт ещё не действовал")

    bad = _wait(jobs.submit("t", "fail", boom, act_code="X2"))
    assert bad.status == "failed" and "не действовал" in bad.error
    assert "X1" not in jobs.busy_acts() and "X2" not in jobs.busy_acts()
