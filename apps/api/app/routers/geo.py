"""Адреса: города, поиск адреса/дома, жилые комплексы города, адрес по точке на карте.

Поиск людей и их адресов по ФИО намеренно не делается: адрес регистрации — персональные данные.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services.geo import photon
from app.services.geo.cities import BY_ID, CITIES

router = APIRouter(prefix="/geo", tags=["geo"])


def _city(city_id: str | None):
    if not city_id:
        return None
    if city_id not in BY_ID:
        raise HTTPException(404, "unknown city")
    return BY_ID[city_id]


async def _safe(coro):
    try:
        return await coro
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(502, f"geocoder unavailable: {type(e).__name__}") from e


@router.get("/cities")
async def cities() -> list[dict]:
    return [c.public() for c in CITIES]


@router.get("/search")
async def search(q: str = Query(min_length=2, max_length=200), city: str | None = None, limit: int = 10) -> list[dict]:
    places = await _safe(photon.search(q, _city(city), min(max(limit, 1), 20)))
    return [p.public() for p in places]


@router.get("/complexes")
async def complexes(city: str, q: str | None = Query(default=None, max_length=100)) -> list[dict]:
    places = await _safe(photon.complexes(_city(city), q))
    return [p.public() for p in places]


@router.get("/reverse")
async def reverse(lat: float = Query(ge=40, le=56), lon: float = Query(ge=46, le=88)) -> dict | None:
    place = await _safe(photon.reverse(lat, lon))
    return place.public() if place else None
