"""CLI ингеста законов.

  python -m ingest fetch ZHO                 # отрендерить kk+ru с Adilet и сохранить в кэш
  python -m ingest parse ZHO                 # разобрать кэш и показать статистику (без БД)
  python -m ingest load ZHO                  # разобрать кэш и записать редакцию в PostgreSQL
  python -m ingest load ZHO --ru-file a.html --kk-file b.html   # из своих файлов
  python -m ingest index ZHO                 # нарезать на чанки, посчитать эмбеддинги, записать в Qdrant
  python -m ingest history ZHO --at 2018-01-01 --at 2020-01-01   # исторические редакции на даты
  python -m ingest editions ZHO              # показать хронологию редакций с Adilet
  python -m ingest graph ALL                 # граф ссылок между пунктами (legal_refs); после load — автоматически
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

from app.core.config import get_settings
from ingest.adilet.fetcher import fetch_act, read_cached
from ingest.adilet.parser import merge_languages, parse_adilet_html
from ingest.loader import load_act, source_hash
from ingest.sources import load_sources


def _read_html(args, src, lang: str) -> str | None:
    explicit = getattr(args, f"{lang}_file")
    if explicit:
        return Path(explicit).read_text(encoding="utf-8")
    cached = read_cached(get_settings().adilet_cache_dir, src, lang)
    return cached.html if cached else None


def _parse(args, src):
    ru_html = _read_html(args, src, "ru")
    if ru_html is None:
        raise SystemExit(f"Нет русского текста {src.code}: сначала `python -m ingest fetch {src.code}`")
    kk_html = _read_html(args, src, "kk")
    ru = parse_adilet_html(ru_html, "ru")
    kk = parse_adilet_html(kk_html, "kk") if kk_html else None
    merged, merge_warnings = merge_languages(ru, kk)
    warnings = ru.warnings + (kk.warnings if kk else []) + merge_warnings
    return merged, warnings, source_hash(ru_html, kk_html)


def _print_stats(code: str, merged, warnings) -> None:
    counts = Counter(u.unit_type for u in merged)
    with_kk = sum(1 for u in merged if u.text_kk or u.heading_kk)
    repealed = sum(1 for u in merged if u.is_repealed)
    print(f"{code}: {len(merged)} единиц — " + ", ".join(f"{k}={v}" for k, v in counts.most_common()))
    print(f"  с казахским текстом: {with_kk}, утратили силу/исключены: {repealed}")
    for w in warnings[:20]:
        print(f"  ! {w}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "parse", "load", "index", "history", "editions", "dates", "graph"):
        p = sub.add_parser(name)
        p.add_argument("code")
        p.add_argument("--ru-file")
        p.add_argument("--kk-file")
        p.add_argument("--at", action="append", default=[], help="дата ГГГГ-ММ-ДД (для history)")
        p.add_argument("--all", action="store_true", help="history: все редакции из хронологии Adilet")
    args = parser.parse_args()

    sources = load_sources()
    if args.cmd == "dates":
        _fix_dates(sources, args.code.upper(), get_settings(), at=args.at)
        return
    if args.cmd == "graph":
        _graph(None if args.code.upper() == "ALL" else args.code.upper())
        return
    src = sources.get(args.code.upper())
    if src is None:
        raise SystemExit(f"Неизвестный акт {args.code}. Доступны: {', '.join(sources)}")

    settings = get_settings()
    if args.cmd == "fetch":
        pages = fetch_act(src, settings.adilet_cache_dir, delay_sec=settings.adilet_request_delay_sec)
        for lang, page in pages.items():
            print(f"{lang}: {len(page.html):,} байт, sha256 {page.sha256[:12]} → {settings.adilet_cache_dir}")
        return

    if args.cmd in ("editions", "history"):
        _history(args, src, settings)
        return

    if args.cmd == "index":
        from app.db.session import SessionLocal, engine
        from ingest.indexer import index_act

        async def run_index():
            async with SessionLocal() as session:
                stats = await index_act(session, src.code)
            await engine.dispose()
            print(stats)

        asyncio.run(run_index())
        return

    merged, warnings, content_hash = _parse(args, src)
    _print_stats(src.code, merged, warnings)
    if args.cmd == "parse":
        return

    from app.db.session import SessionLocal, engine

    async def run():
        async with SessionLocal() as session:
            result = await load_act(session, src, merged, content_hash)
            from app.services.rag.graph import build_all

            await build_all(session, src.code)
        await engine.dispose()
        print(f"{result.act_code}: {result.message} (version {result.version_id}, единиц {result.units})")

    asyncio.run(run())


def _graph(code: str | None) -> None:
    from app.db.session import SessionLocal, engine
    from app.services.rag.graph import build_all

    async def run():
        async with SessionLocal() as session:
            stats = await build_all(session, code)
        await engine.dispose()
        for k, n in stats.items():
            print(f"{k}: {n} ссылок")
        print(f"всего: {sum(stats.values())}")

    asyncio.run(run())


def _fix_dates(sources, code: str, settings, at: list[str] | None = None) -> None:
    """Дата начала действующей редакции = дата из хронологии Adilet (а не день загрузки).

    Обновляет PostgreSQL и поля valid_from в Qdrant без пересчёта векторов. code=ALL — все акты.
    """
    from qdrant_client import models as qm

    from app.db.session import SessionLocal, engine
    from app.services.rag import vector_store as vs
    from ingest.adilet.versions import fetch_versions
    from ingest.loader import set_current_valid_from

    codes = [c for c in sources if sources[c].enabled] if code == "ALL" else [code]
    found = {}
    if at:  # дата уже известна (сверена на Adilet) — без браузера, например внутри контейнера на сервере
        from datetime import date

        found = {code: date.fromisoformat(at[0])}
        print(f"{code}: действующая редакция с {found[code]} (дата задана вручную)")
        codes = []
    for c in codes:
        eds = fetch_versions(sources[c].adilet_id)
        cur = next((e for e in eds if e.is_current), eds[-1])
        found[c] = cur.revision_date
        print(f"{c}: действующая редакция с {cur.revision_date} (всего редакций {len(eds)})")

    async def run():
        from sqlalchemy import select

        from app.db.models import ActVersion, LegalAct

        client = vs.get_client()
        async with SessionLocal() as session:
            for c, d in found.items():
                await set_current_valid_from(session, c, d)
                vid = (await session.execute(select(ActVersion.id).join(LegalAct, LegalAct.id == ActVersion.act_id)
                                             .where(LegalAct.code == c, ActVersion.is_current))).scalar_one()
                client.set_payload(vs.COLLECTION, payload={"valid_from": d.isoformat(), "valid_from_i": vs.date_int(d)},
                                   points=qm.Filter(must=[qm.FieldCondition(key="version_id",
                                                                            match=qm.MatchValue(value=str(vid)))]))
        await engine.dispose()

    asyncio.run(run())


def _history(args, src, settings) -> None:
    import dataclasses
    from datetime import date

    from ingest.adilet.versions import edition_at, fetch_versions

    editions = fetch_versions(src.adilet_id)
    if args.cmd == "editions":
        for e in editions:
            print(f"{e.revision_date}  {e.document_id}{'  ← действующая' if e.is_current else ''}")
        print(f"всего редакций: {len(editions)}")
        return

    from app.db.session import SessionLocal, engine
    from ingest.indexer import index_version
    from ingest.loader import load_historical_version, set_current_valid_from

    current = next((e for e in editions if e.is_current), editions[-1])
    if args.all:
        args.at = [e.revision_date.isoformat() for e in editions if e.document_id != current.document_id]
    picked = []
    for raw in args.at:
        found = edition_at(editions, date.fromisoformat(raw))
        if found is None:
            print(f"{raw}: закон ещё не принят")
            continue
        ed, nxt = found
        if ed.document_id == current.document_id:
            print(f"{raw}: действовала текущая редакция — уже в базе")
            continue
        if ed not in [p[0] for p in picked]:
            picked.append((ed, nxt))

    # 1) скачать тексты редакций (Playwright — синхронно, до asyncio)
    prepared = []
    for ed, nxt in picked:
        ed_src = dataclasses.replace(src, adilet_id=ed.document_id)
        fetch_act(ed_src, settings.adilet_cache_dir, delay_sec=settings.adilet_request_delay_sec, use_cache=True)
        ru_html = read_cached(settings.adilet_cache_dir, ed_src, "ru").html
        kk_page = read_cached(settings.adilet_cache_dir, ed_src, "kk")
        ru = parse_adilet_html(ru_html, "ru")
        kk = parse_adilet_html(kk_page.html, "kk") if kk_page else None
        merged, _ = merge_languages(ru, kk)
        prepared.append((ed, nxt, merged, source_hash(ru_html, kk_page.html if kk_page else None)))

    # 2) записать в PostgreSQL и проиндексировать (векторы неизменившихся пунктов переиспользуются)
    async def run():
        async with SessionLocal() as session:
            await set_current_valid_from(session, src.code, current.revision_date)
            for ed, nxt, merged, chash in prepared:
                res = await load_historical_version(session, src, merged, chash, ed.revision_date, nxt)
                print(f"{ed.revision_date} → {nxt or 'по сей день'}: {res.message}, единиц {res.units}")
                print("   ", await index_version(session, src.code, res.version_id))
            print("   current:", await index_version(session, src.code, None))
        await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
