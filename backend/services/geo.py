from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float


def amap_text(value: object) -> str | None:
    """高德缺字段时常返回 []，不能当字符串用。"""
    if value is None or value == []:
        return None
    if isinstance(value, list):
        if not value:
            return None
        first = value[0]
        if not isinstance(first, str):
            return None
        text = first.strip()
        return text or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def parse_amap_location(value: object) -> GeoPoint | None:
    """高德 location 为「经度,纬度」，经度在前。"""
    text = amap_text(value)
    if not text:
        return None
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        longitude = float(parts[0].strip())
        latitude = float(parts[1].strip())
    except ValueError:
        return None
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        return None
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        return None
    return GeoPoint(longitude=longitude, latitude=latitude)


def format_amap_location(point: GeoPoint) -> str:
    return f"{point.longitude:.6f},{point.latitude:.6f}"


def midpoint(point_a: GeoPoint, point_b: GeoPoint) -> GeoPoint:
    """经度、纬度分别算术平均。这不是等时中点。"""
    return GeoPoint(
        longitude=(point_a.longitude + point_b.longitude) / 2.0,
        latitude=(point_a.latitude + point_b.latitude) / 2.0,
    )


def haversine_m(point_a: GeoPoint, point_b: GeoPoint) -> float:
    radius = EARTH_RADIUS_M
    lat1 = math.radians(point_a.latitude)
    lat2 = math.radians(point_b.latitude)
    d_lat = math.radians(point_b.latitude - point_a.latitude)
    d_lng = math.radians(point_b.longitude - point_a.longitude)
    chord = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2.0) ** 2
    )
    return 2.0 * radius * math.atan2(math.sqrt(chord), math.sqrt(1.0 - chord))


def parse_amap_distance_m(value: object) -> float | None:
    text = amap_text(value)
    if text is None:
        return None
    try:
        distance = float(text)
    except ValueError:
        return None
    if not math.isfinite(distance) or distance < 0:
        return None
    return distance
