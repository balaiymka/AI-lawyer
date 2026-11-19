"""Получение текста акта с adilet.zan.kz.

Сайт — SPA: обычный HTTP-запрос возвращает пустую оболочку, текст появляется после выполнения JS.
Поэтому страница рендерится headless-браузером (Playwright), как у обычного посетителя,
и сохраняется только контейнер с текстом акта. Вежливость: кэш на диске, пауза между запросами,
один запрос за раз.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ingest.sources import ActSource

CONTENT_SELECTOR = ".law-classic-content"
USER_AGENT = "zhkh24-ingest/0.1 (legal research bot; low rate)"


@dataclass
class FetchedPage:
    lang: str
    url: str
    html: str
    sha256: str
    fetched_at: str


def _cache_paths(cache_dir: Path, source: ActSource, lang: str) -> tuple[Path, Path]:
    base = cache_dir / f"{source.adilet_id}_{lang}"
    return base.with_suffix(".html"), base.with_suffix(".json")


def read_cached(cache_dir: Path, source: ActSource, lang: str) -> FetchedPage | None:
    html_path, meta_path = _cache_paths(cache_dir, source, lang)
    if not html_path.exists() or not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return FetchedPage(html=html_path.read_text(encoding="utf-8"), **meta)


def fetch_act(
    source: ActSource,
    cache_dir: Path,
    langs: tuple[str, ...] = ("ru", "kk"),
    delay_sec: float = 3.0,
    use_cache: bool = False,
) -> dict[str, FetchedPage]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Нужен Playwright: pip install -e '.[ingest]' && playwright install chromium"
        ) from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[str, FetchedPage] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(user_agent=USER_AGENT, locale="ru-RU")
        page = context.new_page()
        for i, lang in enumerate(langs):
            if use_cache and (cached := read_cached(cache_dir, source, lang)):
                pages[lang] = cached
                continue
            if i:
                time.sleep(delay_sec)
            url = source.url(lang)
            page.goto(url, wait_until="networkidle", timeout=120_000)
            page.wait_for_selector(f"{CONTENT_SELECTOR} div.law-paragraph", timeout=120_000)
            html = page.inner_html(CONTENT_SELECTOR)
            html = f'<div class="law-classic-content">{html}</div>'
            fetched = FetchedPage(
                lang=lang,
                url=url,
                html=html,
                sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            html_path, meta_path = _cache_paths(cache_dir, source, lang)
            html_path.write_text(html, encoding="utf-8")
            meta = {k: v for k, v in fetched.__dict__.items() if k != "html"}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            pages[lang] = fetched
        browser.close()
    return pages
