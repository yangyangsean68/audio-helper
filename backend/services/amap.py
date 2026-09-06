from __future__ import annotations

import logging

from typing import NoReturn

import httpx

from config import settings
from errors import AppError
from services.geo import GeoPoint, format_amap_location
from services.location_match import normalize_city

logger = logging.getLogger(__name__)
STAGE = "search"
AROUND_OFFSET = 20
ENGINE_DATA_ERROR = "30001"


class AmapStatusError(Exception):
    def __init__(self, infocode: str, info: str) -> None:
        super().__init__(info)
        self.infocode = infocode
        self.info = info


def amap_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        settings.amap_timeout_seconds,
        connect=settings.amap_connect_timeout_seconds,
    )


def amap_transport() -> httpx.AsyncHTTPTransport:
    # Windows 上优先走 IPv4，避免 IPv6 握手拖到整段预算被掐掉。
    return httpx.AsyncHTTPTransport(local_address="0.0.0.0")


def amap_city_name(city: str) -> str:
    text = normalize_city(city)
    if not text.endswith("市"):
        return f"{text}市"
    return text


def _raise_http() -> NoReturn:
    raise AppError(502, "UPSTREAM_ERROR", "找店服务暂时失败，请稍后重试。", STAGE)


def parse_amap_payload(payload: object, call: str) -> dict:
    if not isinstance(payload, dict):
        _raise_http()
    status = payload.get("status")
    info = str(payload.get("info") or "")
    infocode = str(payload.get("infocode") or "")
    if status != "1":
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR infocode=%s info=%s call=%s",
            STAGE,
            infocode,
            info,
            call,
        )
        raise AmapStatusError(infocode, info)
    return payload


async def _amap_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    call: str,
) -> dict:
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT reason=%s_timeout", STAGE, call)
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "找店超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=%s error_code=UPSTREAM_ERROR reason=%s_http", STAGE, call)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "找店服务暂时失败，请稍后重试。",
            STAGE,
        ) from exc

    if response.status_code != 200:
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR http_status=%s call=%s",
            STAGE,
            response.status_code,
            call,
        )
        _raise_http()
    try:
        return parse_amap_payload(response.json(), call)
    except ValueError as exc:
        raise AppError(502, "UPSTREAM_ERROR", "找店服务返回异常。", STAGE) from exc


async def geocode_raw(
    client: httpx.AsyncClient,
    *,
    city: str,
    address: str,
) -> object:
    city_n = normalize_city(city)
    params = {
        "key": settings.amap_api_key,
        "address": address,
        "city": city_n,
    }
    try:
        payload = await _amap_get(client, settings.amap_geo_url, params, "geocode")
    except AmapStatusError as exc:
        if exc.infocode != ENGINE_DATA_ERROR:
            _raise_http()
        prefixed = address if address.startswith(city_n) else f"{city_n}{address}"
        retry_params = {
            "key": settings.amap_api_key,
            "address": prefixed,
        }
        logger.info("stage=%s call=geocode retry=without_city", STAGE)
        try:
            payload = await _amap_get(
                client, settings.amap_geo_url, retry_params, "geocode"
            )
        except AmapStatusError:
            _raise_http()
    return payload.get("geocodes")


async def around_raw(
    client: httpx.AsyncClient,
    *,
    center: GeoPoint,
    keywords: str,
    city: str,
    radius_m: int,
) -> object:
    params = {
        "key": settings.amap_api_key,
        "location": format_amap_location(center),
        "keywords": keywords,
        "radius": radius_m,
        "offset": AROUND_OFFSET,
        "city": amap_city_name(city),
        "citylimit": "true",
    }
    try:
        payload = await _amap_get(client, settings.amap_around_url, params, "around")
    except AmapStatusError as exc:
        if exc.infocode != ENGINE_DATA_ERROR:
            _raise_http()
        retry_params = dict(params)
        retry_params.pop("citylimit", None)
        logger.info("stage=%s call=around retry=without_citylimit", STAGE)
        try:
            payload = await _amap_get(
                client, settings.amap_around_url, retry_params, "around"
            )
        except AmapStatusError:
            _raise_http()
    return payload.get("pois")
