from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import settings
from errors import AppError
from services.geo import GeoPoint
from services.location_match import GeocodeHit
from services.poi_filter import PlacePoi

SEARCH_ID_PATTERN = re.compile(
    r"^sch_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass(frozen=True)
class StoredSearch:
    search_id: str
    created_at: datetime
    midpoint: GeoPoint
    pois: list[PlacePoi]
    radius_m: int


def search_dir() -> Path:
    path = settings.storage_dir / "search"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_search_id() -> str:
    return f"sch_{uuid.uuid4()}"


def _meta_path(search_id: str) -> Path:
    return search_dir() / f"{search_id}.json"


def _is_expired(created_at: datetime) -> bool:
    return datetime.now(timezone.utc) - created_at > timedelta(hours=settings.audio_ttl_hours)


def _point_payload(point: GeoPoint) -> dict:
    return {"longitude": point.longitude, "latitude": point.latitude}


def _hit_payload(hit: GeocodeHit) -> dict:
    return {
        "formatted_address": hit.formatted_address,
        "level": hit.level,
        "longitude": hit.point.longitude,
        "latitude": hit.point.latitude,
    }


def commit_search(
    *,
    city_a: str,
    address_a: str,
    city_b: str,
    address_b: str,
    category: str,
    hit_a: GeocodeHit,
    hit_b: GeocodeHit,
    midpoint: GeoPoint,
    radius_m: int,
    pois: list[PlacePoi],
) -> StoredSearch:
    search_id = new_search_id()
    created_at = datetime.now(timezone.utc)
    payload = {
        "search_id": search_id,
        "created_at": created_at.isoformat(),
        "city_a": city_a,
        "address_a": address_a,
        "city_b": city_b,
        "address_b": address_b,
        "category": category,
        "point_a": _hit_payload(hit_a),
        "point_b": _hit_payload(hit_b),
        "midpoint": _point_payload(midpoint),
        "radius_m": radius_m,
        "pois": [
            {
                "name": poi.name,
                "address": poi.address,
                "distance_to_midpoint_m": poi.distance_to_midpoint_m,
                "longitude": poi.point.longitude,
                "latitude": poi.point.latitude,
            }
            for poi in pois
        ],
    }
    _meta_path(search_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return StoredSearch(
        search_id=search_id,
        created_at=created_at,
        midpoint=midpoint,
        pois=pois,
        radius_m=radius_m,
    )


def get_search(search_id: str) -> dict:
    """读取临时搜店结果。不存在或超过 24 小时视为无效，供后续 /finalize 使用。"""
    if not SEARCH_ID_PATTERN.match(search_id):
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", "finalize")
    meta_file = _meta_path(search_id)
    if not meta_file.exists():
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", "finalize")
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", "finalize") from exc
    if _is_expired(created_at):
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", "finalize")
    return payload
