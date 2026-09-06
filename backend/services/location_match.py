from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from errors import AppError
from services.geo import GeoPoint, amap_text, haversine_m, parse_amap_location

logger = logging.getLogger(__name__)
STAGE = "search"
SAME_PLACE_MAX_M = 250.0

ACCEPTED_LEVELS = {
    "兴趣点",
    "门牌号",
    "公交地铁站点",
    "门址",
    "单元号",
    "住宅区",
    "道路交叉路口",
}

LEVEL_RANK = {
    "门牌号": 0,
    "门址": 1,
    "单元号": 2,
    "公交地铁站点": 3,
    "兴趣点": 4,
    "住宅区": 5,
    "道路交叉路口": 6,
}

_PAREN = re.compile(r"[（(][^）)]*[）)]")
_ADMIN_CHARS = re.compile(r"[省市区县\s]+")
_SUFFIXES = ("地铁站", "高铁站", "火车站", "汽车站", "公交站")


@dataclass(frozen=True)
class GeocodeHit:
    formatted_address: str
    name: str | None
    level: str
    city: str | None
    province: str | None
    point: GeoPoint


def normalize_city(value: str) -> str:
    text = value.strip()
    if text.endswith("市") and len(text) > 1:
        text = text[:-1]
    return text


def normalize_place_name(name: str) -> str:
    text = _PAREN.sub("", name)
    return re.sub(r"\s+", "", text).strip()


def compact_place(text: str) -> str:
    stripped = _PAREN.sub("", text)
    return _ADMIN_CHARS.sub("", stripped)


def core_query(address: str, city: str | None = None) -> str:
    text = compact_place(address)
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
            break
    if city:
        city_n = compact_place(normalize_city(city))
        if city_n and text.startswith(city_n) and len(text) - len(city_n) >= 2:
            text = text[len(city_n) :]
    return text


def address_matches(
    user_address: str,
    formatted: str | None,
    poi_name: str | None,
    city: str | None = None,
) -> bool:
    core = core_query(user_address, city)
    if len(core) < 2:
        return False
    haystack = compact_place((formatted or "") + (poi_name or ""))
    if len(haystack) < 2:
        return False
    if core in haystack or haystack in core:
        return True
    if f"{core}站" in haystack:
        return True
    return False


def city_matches(requested: str, geocode_city: str | None, geocode_province: str | None) -> bool:
    want = normalize_city(requested)
    got_city = normalize_city(geocode_city) if geocode_city else ""
    got_province = normalize_city(geocode_province) if geocode_province else ""
    if got_city:
        return got_city == want or want in got_city or got_city in want
    if got_province:
        return got_province == want or want in got_province or got_province in want
    return False


def parse_geocode_hit(raw: object) -> GeocodeHit | None:
    if not isinstance(raw, dict):
        return None
    point = parse_amap_location(raw.get("location"))
    level = amap_text(raw.get("level"))
    formatted = amap_text(raw.get("formatted_address"))
    if point is None or not level or not formatted:
        return None
    return GeocodeHit(
        formatted_address=formatted,
        name=amap_text(raw.get("name")),
        level=level,
        city=amap_text(raw.get("city")),
        province=amap_text(raw.get("province")),
        point=point,
    )


def _facility_key(hit: GeocodeHit, city: str | None = None) -> str:
    if hit.name:
        return core_query(hit.name, city)
    return core_query(hit.formatted_address, city)


def _match_score(user_address: str, hit: GeocodeHit, city: str) -> int:
    """名称越接近用户说法分数越高。不能凭距离远近选点。"""
    user_full = normalize_place_name(user_address)
    user_core = core_query(user_address, city)
    name = normalize_place_name(hit.name) if hit.name else ""
    formatted = compact_place(hit.formatted_address)
    score = 1
    if name:
        name_core = core_query(name, city)
        if name in {user_full, user_core} or name_core == user_core:
            score = 3
    if score < 2 and user_full and (formatted == user_full or formatted.endswith(user_full)):
        score = 2
    if score < 2 and user_core and (
        formatted.endswith(user_core)
        or formatted.endswith(user_core + "站")
        or user_core in formatted
    ):
        score = 2
    if "地铁" in user_address and hit.level == "公交地铁站点":
        score += 1
    return score


def _same_facility(hits: list[GeocodeHit], city: str) -> bool:
    keys = {_facility_key(hit, city) for hit in hits}
    if len(keys) != 1:
        return False
    for index, left in enumerate(hits):
        for right in hits[index + 1 :]:
            if haversine_m(left.point, right.point) > SAME_PLACE_MAX_M:
                return False
    return True


def _pick_finest(hits: list[GeocodeHit]) -> GeocodeHit:
    return min(hits, key=lambda hit: LEVEL_RANK.get(hit.level, 99))


def _pick_unique(requested_address: str, requested_city: str, usable: list[GeocodeHit]) -> GeocodeHit:
    if len(usable) == 1:
        return usable[0]
    best_score = max(_match_score(requested_address, hit, requested_city) for hit in usable)
    best = [
        hit
        for hit in usable
        if _match_score(requested_address, hit, requested_city) == best_score
    ]
    if len(best) == 1:
        return best[0]
    if "地铁" in requested_address:
        subway = [hit for hit in best if hit.level == "公交地铁站点"]
        if len(subway) == 1:
            return subway[0]
        if subway:
            best = subway
    if _same_facility(best, requested_city):
        return _pick_finest(best)
    logger.info(
        "stage=%s error_code=LOCATION_AMBIGUOUS candidates=%s",
        STAGE,
        [
            {
                "level": hit.level,
                "name": hit.name,
                "formatted_address": hit.formatted_address,
            }
            for hit in best
        ],
    )
    raise AppError(
        422,
        "LOCATION_AMBIGUOUS",
        "地点不够明确，请补充具体地点后重新表达。",
        STAGE,
    )


def resolve_location(requested_city: str, requested_address: str, raw_geocodes: object) -> GeocodeHit:
    if not isinstance(raw_geocodes, list) or not raw_geocodes:
        raise AppError(
            422,
            "LOCATION_NOT_FOUND",
            "无法定位该地点，请说得更具体后重新表达。",
            STAGE,
        )

    parsed = [hit for item in raw_geocodes if (hit := parse_geocode_hit(item))]
    if not parsed:
        raise AppError(
            422,
            "LOCATION_NOT_FOUND",
            "无法定位该地点，请说得更具体后重新表达。",
            STAGE,
        )

    in_city = [
        hit
        for hit in parsed
        if city_matches(requested_city, hit.city, hit.province)
    ]
    if not in_city:
        raise AppError(
            422,
            "LOCATION_CITY_MISMATCH",
            "定位到的城市与所说城市不一致，请重新表达。",
            STAGE,
        )

    usable = [
        hit
        for hit in in_city
        if hit.level in ACCEPTED_LEVELS
        and address_matches(
            requested_address, hit.formatted_address, hit.name, requested_city
        )
    ]
    if not usable:
        logger.info(
            "stage=%s error_code=LOCATION_AMBIGUOUS reason=no_usable in_city=%s",
            STAGE,
            [
                {
                    "level": hit.level,
                    "name": hit.name,
                    "formatted_address": hit.formatted_address,
                }
                for hit in in_city
            ],
        )
        raise AppError(
            422,
            "LOCATION_AMBIGUOUS",
            "地点不够明确，请补充具体地点后重新表达。",
            STAGE,
        )
    return _pick_unique(requested_address, requested_city, usable)
