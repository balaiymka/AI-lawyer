"""Редакции законов: хронология Adilet, выбор редакции на дату, фильтр поиска по дате события."""

import uuid
from datetime import date

from qdrant_client import QdrantClient, models

from app.services.rag import vector_store as vs
from ingest.adilet.versions import edition_at, parse_versions

PAYLOAD = {"versions": [
    {"document_id": "cur", "revision_date": "2026-09-13T18:00:00.000Z", "is_current": True, "created_at": "2026-09-14"},
    {"document_id": "v2020", "revision_date": "2019-12-31T18:00:00.000Z", "is_current": False, "created_at": "a"},
    {"document_id": "v2018", "revision_date": "2017-12-31T18:00:00.000Z", "is_current": False, "created_at": "a"},
    {"document_id": "v2020b", "revision_date": "2020-01-06T18:00:00.000Z", "is_current": False, "created_at": "a"},
]}


def test_parse_versions_converts_almaty_dates_and_sorts():
    eds = parse_versions(PAYLOAD)
    assert [(e.document_id, e.revision_date) for e in eds] == [
        ("v2018", date(2018, 1, 1)), ("v2020", date(2020, 1, 1)), ("v2020b", date(2020, 1, 7)), ("cur", date(2026, 9, 14))]
    assert eds[-1].is_current


def test_edition_at_returns_edition_and_its_end():
    eds = parse_versions(PAYLOAD)
    ed, nxt = edition_at(eds, date(2020, 1, 3))
    assert ed.document_id == "v2020" and nxt == date(2020, 1, 7)
    ed, nxt = edition_at(eds, date(2026, 11, 1))
    assert ed.document_id == "cur" and nxt is None
    assert edition_at(eds, date(2010, 1, 1)) is None


def test_time_filter_picks_edition_valid_on_event_date():
    client = QdrantClient(":memory:")
    client.create_collection(vs.COLLECTION, vectors_config={vs.DENSE: models.VectorParams(size=2, distance=models.Distance.COSINE)})
    rows = [
        ("zho-2018", "ZHO", True, False, date(2018, 1, 1), date(2018, 5, 24)),
        ("zho-2020", "ZHO", True, False, date(2020, 1, 1), date(2020, 1, 7)),
        ("zho-now", "ZHO", True, True, date(2026, 9, 14), None),
        ("gk-now", "GK_GEN", False, True, date(2026, 11, 15), None),  # истории нет — участвует всегда
    ]
    client.upsert(vs.COLLECTION, points=[
        models.PointStruct(id=str(uuid.uuid4()), vector={vs.DENSE: [1.0, 0.0]},
                           payload={"tag": tag, "act_code": act, "temporal": temporal, "is_current": cur,
                                    "valid_from_i": vs.date_int(f), "valid_to_i": vs.date_int(t)})
        for tag, act, temporal, cur, f, t in rows])

    def tags(as_of):
        pts, _ = client.scroll(vs.COLLECTION, scroll_filter=vs.time_filter(as_of), limit=10, with_payload=True)
        return sorted(p.payload["tag"] for p in pts)

    assert tags(None) == ["gk-now", "zho-now"]
    assert tags(date(2018, 3, 1)) == ["gk-now", "zho-2018"]
    assert tags(date(2020, 1, 5)) == ["gk-now", "zho-2020"]
    assert tags(date(2026, 10, 1)) == ["gk-now", "zho-now"]
    assert tags(date(2019, 6, 1)) == ["gk-now"]  # на эту дату редакция ЖО не загружена

    # для ЖО на 2019 год берём ближайшую раннюю загруженную редакцию — дата задаётся отдельно для акта
    pts, _ = client.scroll(vs.COLLECTION, scroll_filter=vs.time_filter(date(2019, 6, 1), {"ZHO": date(2018, 1, 1)}),
                           limit=10, with_payload=True)
    assert sorted(p.payload["tag"] for p in pts) == ["gk-now", "zho-2018"]
