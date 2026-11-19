"""Фоновые задачи админки: выполняются по одной в отдельном потоке внутри процесса API.

Так индексация пишет в ту же базу поиска, которую читает API (встроенный Qdrant нельзя открыть из двух
процессов), и не мешает отвечать пользователям. Журнал задач хранится в памяти процесса.
"""

from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

MAX_JOBS = 100
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="admin-job")
_lock = threading.Lock()


@dataclass
class Job:
    id: str
    kind: str
    title: str
    act_code: str | None
    created_by: str | None
    status: str = "queued"  # queued | running | done | failed
    log: list[str] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None

    def public(self, with_log: bool = True) -> dict:
        d = {k: getattr(self, k) for k in ("id", "kind", "title", "act_code", "created_by", "status", "result",
                                           "error", "created_at", "finished_at")}
        d["log"] = self.log[-200:] if with_log else self.log[-3:]
        return d


_jobs: OrderedDict[str, Job] = OrderedDict()


def submit(kind: str, title: str, fn: Callable[[Callable[[str], None]], Any], *, act_code: str | None = None,
           created_by: str | None = None) -> Job:
    """fn(log) выполняется в рабочем потоке; если fn — корутина-функция, для неё создаётся свой event loop."""
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title, act_code=act_code, created_by=created_by)
    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_JOBS:
            _jobs.popitem(last=False)

    def log(msg: str) -> None:
        job.log.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")

    def run() -> None:
        job.status = "running"
        log("старт")
        try:
            res = fn(log)
            if asyncio.iscoroutine(res):
                res = asyncio.run(res)
            job.result, job.status = res, "done"
            log("готово")
        except Exception as e:  # noqa: BLE001 — ошибка задачи показывается в админке
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            log("ошибка: " + job.error)
            job.log.extend(traceback.format_exc().splitlines()[-6:])
        finally:
            job.finished_at = datetime.now(timezone.utc).isoformat()

    _executor.submit(run)
    return job


def list_jobs() -> list[dict]:
    return [j.public(with_log=False) for j in reversed(_jobs.values())]


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def busy_acts() -> set[str]:
    return {j.act_code for j in _jobs.values() if j.status in ("queued", "running") and j.act_code}
