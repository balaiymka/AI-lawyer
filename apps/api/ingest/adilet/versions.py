"""Хронология редакций акта на Adilet.

Страница `…/docs/<id>?tab=history` запрашивает `/api/documents/<uuid>/versions` — список редакций с датами.
Каждая редакция открывается как отдельный документ `…/docs/<document_id>` (rus и kaz), поэтому её текст
скачивается тем же фетчером, что и текущая редакция.

Дата в API — полночь по Алматы, записанная в UTC («2019-12-31T18:00Z» = 01.01.2020).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ingest.adilet.fetcher import USER_AGENT

ALMATY = timedelta(hours=6)


@dataclass(frozen=True)
class Edition:
    document_id: str
    revision_date: date  # с этого дня действует редакция
    is_current: bool


def _to_local_date(iso: str) -> date:
    return (datetime.fromisoformat(iso.replace("Z", "+00:00")) + ALMATY).date()


def parse_versions(payload: dict) -> list[Edition]:
    """Список редакций по возрастанию даты; на одну дату — одна редакция (последняя опубликованная)."""
    by_date: dict[date, dict] = {}
    for v in payload.get("versions", []):
        d = _to_local_date(v["revision_date"])
        prev = by_date.get(d)
        if prev is None or v.get("is_current") or v.get("created_at", "") > prev.get("created_at", ""):
            by_date[d] = v
    return [Edition(v["document_id"], d, bool(v.get("is_current"))) for d, v in sorted(by_date.items())]


def fetch_versions(adilet_id: str, lang: str = "rus") -> list[Edition]:
    from playwright.sync_api import sync_playwright

    holder: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)
        page.on("response", lambda r: holder.setdefault("resp", r) if "/versions?" in r.url else None)
        page.goto(f"https://adilet.zan.kz/{lang}/docs/{adilet_id}?tab=history", wait_until="networkidle",
                  timeout=90_000)
        for _ in range(20):
            if "resp" in holder:
                break
            time.sleep(0.5)
        if "resp" not in holder:
            browser.close()
            raise RuntimeError(f"Adilet не отдал хронологию редакций для {adilet_id}")
        payload = json.loads(holder["resp"].text())
        browser.close()
    return parse_versions(payload)


def edition_at(editions: list[Edition], when: date) -> tuple[Edition, date | None] | None:
    """Редакция, действовавшая на дату `when`, и дата, с которой её сменила следующая (None — действует)."""
    chosen = None
    for i, e in enumerate(editions):
        if e.revision_date <= when:
            chosen = i
        else:
            break
    if chosen is None:
        return None
    nxt = editions[chosen + 1].revision_date if chosen + 1 < len(editions) else None
    return editions[chosen], nxt
