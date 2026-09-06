from __future__ import annotations

from dataclasses import dataclass

from services.geo import (
    GeoPoint,
    amap_text,
    haversine_m,
    parse_amap_distance_m,
    parse_amap_location,
)

MAX_POIS = 3


@dataclass(frozen=True)
class PlacePoi:
    name: str
    address: str
    distance_to_midpoint_m: int
    point: GeoPoint


def collect_valid_pois(raw_pois: object, midpoint: GeoPoint) -> list[PlacePoi]:
    if not isinstance(raw_pois, list):
        return []
    collected: list[PlacePoi] = []
    for item in raw_pois:
        if not isinstance(item, dict):
            continue
        name = amap_text(item.get("name"))
        address = amap_text(item.get("address"))
        point = parse_amap_location(item.get("location"))
        if not name or not address:
            continue
        distance = parse_amap_distance_m(item.get("distance"))
        if distance is None:
            if point is None:
                continue
            distance = haversine_m(point, midpoint)
        if point is None:
            continue
        collected.append(
            PlacePoi(
                name=name,
                address=address,
                distance_to_midpoint_m=int(round(distance)),
                point=point,
            )
        )
    collected.sort(key=lambda poi: poi.distance_to_midpoint_m)
    return collected[:MAX_POIS]
