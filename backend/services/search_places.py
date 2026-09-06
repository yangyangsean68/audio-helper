from __future__ import annotations

import asyncio
import logging
import time

import httpx

from config import settings
from errors import AppError
from services.amap import around_raw, geocode_raw, amap_timeout, amap_transport
from services.geo import midpoint
from services.location_match import normalize_city, resolve_location
from services.poi_filter import collect_valid_pois
from services.search_store import StoredSearch, commit_search

logger = logging.getLogger(__name__)
STAGE = "search"
FIRST_RADIUS_M = 2000
EXPAND_RADIUS_M = 5000


async def _search_meeting(
    city_a: str,
    address_a: str,
    city_b: str,
    address_b: str,
    category: str,
) -> StoredSearch:
    city_a = normalize_city(city_a)
    city_b = normalize_city(city_b)
    if city_a != city_b:
        raise AppError(
            422,
            "CROSS_CITY",
            "当前只支持同一座城市内的两人，请重新表达。",
            STAGE,
        )
    if not settings.amap_api_key.strip():
        raise AppError(502, "UPSTREAM_ERROR", "找店服务未配置密钥。", STAGE)

    timeout = amap_timeout()
    async with httpx.AsyncClient(timeout=timeout, transport=amap_transport()) as client:
        geocode_started = time.perf_counter()
        raw_a, raw_b = await asyncio.gather(
            geocode_raw(client, city=city_a, address=address_a),
            geocode_raw(client, city=city_b, address=address_b),
        )
        logger.info(
            "stage=%s step=geocode duration_ms=%s",
            STAGE,
            int((time.perf_counter() - geocode_started) * 1000),
        )
        hit_a = resolve_location(city_a, address_a, raw_a)
        hit_b = resolve_location(city_b, address_b, raw_b)
        center = midpoint(hit_a.point, hit_b.point)
        around_started = time.perf_counter()
        first = collect_valid_pois(
            await around_raw(
                client,
                center=center,
                keywords=category,
                city=city_a,
                radius_m=FIRST_RADIUS_M,
            ),
            center,
        )
        radius_m = FIRST_RADIUS_M
        pois = first
        if not pois:
            pois = collect_valid_pois(
                await around_raw(
                    client,
                    center=center,
                    keywords=category,
                    city=city_a,
                    radius_m=EXPAND_RADIUS_M,
                ),
                center,
            )
            radius_m = EXPAND_RADIUS_M
        logger.info(
            "stage=%s step=around duration_ms=%s radius_m=%s poi_count=%s",
            STAGE,
            int((time.perf_counter() - around_started) * 1000),
            radius_m,
            len(pois),
        )
        if not pois:
            raise AppError(
                422,
                "NO_POI",
                "中点附近没有找到合适的店，请换个地点或类别再试。",
                STAGE,
            )

    stored = commit_search(
        city_a=city_a,
        address_a=address_a,
        city_b=city_b,
        address_b=address_b,
        category=category,
        hit_a=hit_a,
        hit_b=hit_b,
        midpoint=center,
        radius_m=radius_m,
        pois=pois,
    )
    logger.info(
        "stage=%s search_id=%s radius_m=%s poi_count=%s",
        STAGE,
        stored.search_id,
        stored.radius_m,
        len(stored.pois),
    )
    return stored


async def search_meeting(
    city_a: str,
    address_a: str,
    city_b: str,
    address_b: str,
    category: str,
) -> StoredSearch:
    try:
        return await asyncio.wait_for(
            _search_meeting(city_a, address_a, city_b, address_b, category),
            timeout=settings.search_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT reason=total_budget", STAGE)
        raise AppError(504, "UPSTREAM_TIMEOUT", "找店超时，请稍后重试。", STAGE) from exc
