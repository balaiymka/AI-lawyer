"""/health без настоящих БД и Qdrant: подменяем сессию и клиента."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.services.rag import vector_store


class FakeResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class FakeSession:
    def __init__(self, fail=False, laws=(15, 31, 15, datetime(2026, 11, 18, tzinfo=timezone.utc))):
        self.fail, self.laws = fail, laws

    async def execute(self, stmt):
        if self.fail:
            raise ConnectionRefusedError("db down")
        return FakeResult(self.laws)


class FakeQdrant:
    def __init__(self, exists=True, points=42000, fail=False):
        self.exists, self.points, self.fail = exists, points, fail

    def collection_exists(self, name):
        if self.fail:
            raise ConnectionError("qdrant down")
        return self.exists

    def count(self, name, exact=False):
        return SimpleNamespace(count=self.points)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(monkeypatch, session, qdrant):
    async def fake_session():
        yield session
    app.dependency_overrides[get_session] = fake_session
    monkeypatch.setattr(vector_store, "get_client", lambda: qdrant)


def test_all_ok(client, monkeypatch):
    use(monkeypatch, FakeSession(), FakeQdrant())
    r = client.get("/health")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok" and body["db"] == "ok"
    assert body["laws"] == {"status": "ok", "acts": 15, "versions": 31, "current_versions": 15,
                            "last_fetched_at": "2026-11-18T00:00:00+00:00"}
    assert body["qdrant"] == {"status": "ok", "points": 42000}
    assert body["llm"] == {"provider": "anthropic", "model": get_settings().llm_model, "ready": True}
    assert set(body["models"]) == {"embedder", "reranker"}


def test_api_key_never_leaks(client, monkeypatch):
    use(monkeypatch, FakeSession(), FakeQdrant())
    assert "test-key" not in client.get("/health").text


def test_db_down_gives_503(client, monkeypatch):
    use(monkeypatch, FakeSession(fail=True), FakeQdrant())
    r = client.get("/health")
    body = r.json()
    assert r.status_code == 503 and body["status"] == "down"
    assert body["db"] == "error: ConnectionRefusedError" and body["laws"] == {"status": "skipped"}


def test_qdrant_down_gives_503(client, monkeypatch):
    use(monkeypatch, FakeSession(), FakeQdrant(fail=True))
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["qdrant"] == {"status": "error: ConnectionError"}


def test_missing_collection_is_down(client, monkeypatch):
    use(monkeypatch, FakeSession(), FakeQdrant(exists=False))
    assert client.get("/health").status_code == 503


def test_degraded_when_act_has_no_current_version(client, monkeypatch):
    use(monkeypatch, FakeSession(laws=(15, 31, 14, None)), FakeQdrant())
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "degraded"
    assert r.json()["laws"]["status"] == "warning"


def test_degraded_without_llm_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    use(monkeypatch, FakeSession(), FakeQdrant())
    body = client.get("/health").json()
    assert body["status"] == "degraded" and body["llm"]["ready"] is False
