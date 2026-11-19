"""Поиск адресов и жилых комплексов через Photon (геокодер на данных OpenStreetMap).

Запросы идут через наш API: кэш на час, не больше ~2 запросов в секунду к сервису (правила честного
использования публичного Photon). Для продакшена — свой Photon или коммерческий геокодер (например, 2GIS).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass

import httpx

from app.services.geo.cities import City

PHOTON = "https://photon.komoot.io"
USER_AGENT = "zhkh24-portal/0.1"
KZ_BBOX = (46.4, 40.5, 87.4, 55.5)
CACHE_TTL = 3600
COMPLEX_TERMS = ["ЖК", "жилой комплекс", "тұрғын үй кешені", "residential complex"]
COMPLEX_RE = re.compile(r"(^|\s|\")(жк|жилой комплекс|тұрғын үй кешені|residential)", re.I)

_cache: dict[str, tuple[float, list]] = {}
_lock = asyncio.Lock()
_last_call = 0.0


@dataclass
class Place:
    name: str | None
    label: str  # строка адреса для документа
    kind: str  # complex | building | street | city | other
    street: str | None
    housenumber: str | None
    city: str | None
    lat: float
    lon: float

    def public(self) -> dict:
        return asdict(self)


def _kind(p: dict) -> str:
    name = p.get("name") or ""
    if COMPLEX_RE.search(name) or (p.get("osm_key") == "landuse" and p.get("osm_value") == "residential" and name):
        return "complex"
    if p.get("housenumber"):
        return "building"
    if p.get("osm_key") == "highway" or p.get("type") == "street":
        return "street"
    if p.get("osm_key") == "place" and p.get("osm_value") in ("city", "town", "village"):
        return "city"
    return "other"


def _label(p: dict, kind: str) -> str:
    city = p.get("city") or (p.get("name") if kind == "city" else None)
    parts: list[str] = []
    if city:
        parts.append(city)
    if kind == "complex" and p.get("name"):
        parts.append(p["name"])
    if p.get("street"):
        parts.append(p["street"] + (f", {p['housenumber']}" if p.get("housenumber") else ""))
    elif kind not in ("complex", "city") and p.get("name"):
        parts.append(p["name"])
    return ", ".join(parts) or (p.get("name") or "")


def to_place(feature: dict) -> Place:
    p = feature.get("properties", {})
    lon, lat = feature["geometry"]["coordinates"][:2]
    kind = _kind(p)
    return Place(name=p.get("name"), label=_label(p, kind), kind=kind, street=p.get("street"),
                 housenumber=p.get("housenumber"), city=p.get("city"), lat=lat, lon=lon)


async def _get(path: str, params: dict) -> list[dict]:
    global _last_call
    key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    async with _lock:  # не чаще 2 запросов в секунду
        wait = 0.5 - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(PHOTON + path, params=params)
    r.raise_for_status()
    features = r.json().get("features", [])
    _cache[key] = (time.time(), features)
    return features


def _bbox(city: City | None) -> str:
    b = city.bbox if city else KZ_BBOX
    return ",".join(f"{x:.4f}" for x in b)


def _dedupe(places: list[Place]) -> list[Place]:
    seen: set[str] = set()
    out = []
    for p in places:
        k = p.label.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return out


async def search(q: str, city: City | None, limit: int = 10) -> list[Place]:
    params = {"q": q if not city or city.ru.lower() in q.lower() else f"{q} {city.ru}", "limit": limit, "bbox": _bbox(city)}
    return _dedupe([to_place(f) for f in await _get("/api/", params)])


async def complexes(city: City, q: str | None = None) -> list[Place]:
    terms = [f"ЖК {q}"] if q else COMPLEX_TERMS
    found: list[Place] = []
    for t in terms:
        found += [to_place(f) for f in await _get("/api/", {"q": t, "limit": 50, "bbox": _bbox(city)})]
    return sorted(_dedupe([p for p in found if p.kind == "complex"]), key=lambda p: (p.name or "").lower())


async def reverse(lat: float, lon: float) -> Place | None:
    features = await _get("/reverse", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "limit": 1})
    return to_place(features[0]) if features else None
