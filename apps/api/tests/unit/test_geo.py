"""Адреса: разбор ответа Photon, ЖК, кэш и API (без сети — _get подменяется)."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.geo import photon
from app.services.geo.cities import BY_ID


def feat(lon, lat, **props):
    return {"geometry": {"coordinates": [lon, lat]}, "properties": props}


def test_kinds_and_labels():
    b = photon.to_place(feat(76.9, 43.2, osm_key="building", housenumber="150", street="улица Абая", city="Алматы"))
    assert (b.kind, b.label) == ("building", "Алматы, улица Абая, 150")
    c = photon.to_place(feat(71.4, 51.1, name="ЖК Хайвил", osm_key="landuse", osm_value="residential", city="Астана"))
    assert (c.kind, c.label) == ("complex", "Астана, ЖК Хайвил")
    s = photon.to_place(feat(71.4, 51.1, name="проспект Мангилик Ел", osm_key="highway", city="Астана"))
    assert s.kind == "street" and s.label == "Астана, проспект Мангилик Ел"


def test_city_bbox_contains_center():
    for c in BY_ID.values():
        x1, y1, x2, y2 = c.bbox
        assert x1 < c.lon < x2 and y1 < c.lat < y2


def test_api_complexes_dedupes_and_filters(monkeypatch):
    calls = []

    async def fake_get(path, params):
        calls.append(params["q"])
        return [feat(71.4, 51.1, name="ЖК Хайвил", osm_key="landuse", osm_value="residential", city="Астана"),
                feat(71.4, 51.1, name="Школа № 5", osm_key="amenity", city="Астана")]

    monkeypatch.setattr(photon, "_get", fake_get)
    client = TestClient(app)
    r = client.get("/v1/geo/complexes", params={"city": "astana"})
    assert [x["name"] for x in r.json()] == ["ЖК Хайвил"]
    assert len(calls) == len(photon.COMPLEX_TERMS)
    assert client.get("/v1/geo/complexes", params={"city": "nowhere"}).status_code == 404
    assert len(client.get("/v1/geo/cities").json()) == len(BY_ID)


def test_api_reports_geocoder_failure(monkeypatch):
    import httpx

    async def boom(path, params):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(photon, "_get", boom)
    r = TestClient(app).get("/v1/geo/search", params={"q": "абая 10", "city": "almaty"})
    assert r.status_code == 502
