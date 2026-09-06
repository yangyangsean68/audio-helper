import json
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from config import settings
from errors import AppError
from main import app
from services.geo import GeoPoint, haversine_m, midpoint, parse_amap_location
from services.location_match import resolve_location
from services.poi_filter import collect_valid_pois
from services.search_store import SEARCH_ID_PATTERN

client = TestClient(app)

HANGZHOU_EAST = "120.212010,30.290800"
LONGXIANGQIAO = "120.161000,30.259000"
SEARCH_BODY = {
    "city_a": "杭州",
    "address_a": "杭州东站",
    "city_b": "杭州",
    "address_b": "西湖龙翔桥地铁站",
    "category": "咖啡店",
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _geocode_item(formatted, location, level="兴趣点", city="杭州市", name=None):
    item = {
        "formatted_address": formatted,
        "province": "浙江省",
        "city": city,
        "location": location,
        "level": level,
    }
    if name is not None:
        item["name"] = name
    return item


def _ok(geocodes=None, pois=None):
    payload = {"status": "1", "info": "OK", "infocode": "10000"}
    if geocodes is not None:
        payload["geocodes"] = geocodes
    if pois is not None:
        payload["pois"] = pois
    return payload


def _install_amap(monkeypatch, handler):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return handler

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(settings, "amap_api_key", "test-key")
    monkeypatch.setattr("services.search_places.httpx.AsyncClient", Client)


class RecordingHandler:
    def __init__(self, geo_by_address, around_by_radius):
        self.geo_by_address = geo_by_address
        self.around_by_radius = around_by_radius
        self.geo_calls = []
        self.around_calls = []

    async def get(self, url, params=None):
        params = params or {}
        if "geocode" in url:
            self.geo_calls.append(params)
            address = params.get("address")
            return FakeResponse(self.geo_by_address[address])
        self.around_calls.append(params)
        radius = int(params["radius"])
        return FakeResponse(self.around_by_radius[radius])


def test_parse_location_longitude_first():
    point = parse_amap_location(HANGZHOU_EAST)
    assert point is not None
    assert point.longitude == 120.212010
    assert point.latitude == 30.290800


def test_midpoint_is_arithmetic_mean():
    point_a = GeoPoint(120.0, 30.0)
    point_b = GeoPoint(122.0, 32.0)
    center = midpoint(point_a, point_b)
    assert center.longitude == 121.0
    assert center.latitude == 31.0


def test_missing_distance_uses_haversine_not_zero():
    center = GeoPoint(120.0, 30.0)
    shop = GeoPoint(120.01, 30.0)
    expected = int(round(haversine_m(shop, center)))
    assert expected != 0
    pois = collect_valid_pois(
        [
            {
                "name": "某咖啡店",
                "address": "示例路 1 号",
                "location": "120.01,30.0",
                "distance": [],
            }
        ],
        center,
    )
    assert len(pois) == 1
    assert pois[0].distance_to_midpoint_m == expected


def test_amap_distance_preferred_over_haversine():
    center = GeoPoint(120.0, 30.0)
    pois = collect_valid_pois(
        [
            {
                "name": "某咖啡店",
                "address": "示例路 1 号",
                "location": "121.0,31.0",
                "distance": "186",
            }
        ],
        center,
    )
    assert pois[0].distance_to_midpoint_m == 186


def test_drop_poi_without_distance_and_location():
    pois = collect_valid_pois(
        [{"name": "某咖啡店", "address": "示例路 1 号", "location": [], "distance": []}],
        GeoPoint(120.0, 30.0),
    )
    assert pois == []


def test_pois_sorted_and_capped_at_three():
    center = GeoPoint(120.0, 30.0)
    pois = collect_valid_pois(
        [
            {
                "name": "C",
                "address": "路 3 号",
                "location": "120.0,30.0",
                "distance": "900",
            },
            {
                "name": "A",
                "address": "路 1 号",
                "location": "120.0,30.0",
                "distance": "120",
            },
            {
                "name": "D",
                "address": "路 4 号",
                "location": "120.0,30.0",
                "distance": "1200",
            },
            {
                "name": "B",
                "address": "路 2 号",
                "location": "120.0,30.0",
                "distance": "400",
            },
        ],
        center,
    )
    assert [poi.name for poi in pois] == ["A", "B", "C"]
    assert [poi.distance_to_midpoint_m for poi in pois] == [120, 400, 900]


def test_beijing_subway_ignores_district_in_the_middle():
    hit = resolve_location(
        "北京",
        "北京国贸地铁站",
        [
            _geocode_item(
                "北京市朝阳区国贸站",
                "116.4619,39.9092",
                level="公交地铁站点",
            ),
            _geocode_item("北京市朝阳区国贸商城", "116.4610,39.9088", name="国贸商城"),
        ],
    )
    assert hit.level == "公交地铁站点"
    assert "国贸站" in hit.formatted_address


def test_yongtaizhuang_matches_across_district_name():
    hit = resolve_location(
        "北京",
        "北京永泰庄地铁站",
        [
            _geocode_item(
                "北京市海淀区永泰庄",
                "116.3540,40.0210",
                level="公交地铁站点",
            )
        ],
    )
    assert hit.level == "公交地铁站点"


def test_prefer_exact_station_over_nearby_squares():
    hit = resolve_location(
        "杭州",
        "杭州东站",
        [
            _geocode_item("浙江省杭州市上城区杭州东站东广场", "120.2120,30.2908"),
            _geocode_item("浙江省杭州市上城区杭州东站", "120.2160,30.2908"),
            _geocode_item("浙江省杭州市上城区杭州东站西广场", "120.2140,30.2908"),
        ],
    )
    assert hit.formatted_address.endswith("杭州东站")
    assert "广场" not in hit.formatted_address


def test_nearby_different_names_are_ambiguous():
    try:
        resolve_location(
            "杭州",
            "杭州东站",
            [
                _geocode_item("浙江省杭州市上城区杭州东站东广场", "120.2120,30.2908", name="杭州东站东广场"),
                _geocode_item("浙江省杭州市上城区杭州东站西广场", "120.2140,30.2908", name="杭州东站西广场"),
            ],
        )
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "LOCATION_AMBIGUOUS"


def test_same_name_close_candidates_merge():
    hit = resolve_location(
        "杭州",
        "杭州东站",
        [
            _geocode_item("浙江省杭州市上城区杭州东站", "120.2120,30.2908", name="杭州东站"),
            _geocode_item("浙江省杭州市上城区杭州东站(地铁站)", "120.2125,30.2908", name="杭州东站(地铁站)"),
        ],
    )
    assert hit.level == "兴趣点"


def test_same_name_far_apart_is_ambiguous():
    try:
        resolve_location(
            "杭州",
            "杭州东站",
            [
                _geocode_item("浙江省杭州市上城区杭州东站", "120.2120,30.2908", name="杭州东站"),
                _geocode_item("浙江省杭州市上城区杭州东站", "120.2300,30.2908", name="杭州东站"),
            ],
        )
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.code == "LOCATION_AMBIGUOUS"


def test_search_success_saves_created_at(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    handler = RecordingHandler(
        {
            "杭州东站": _ok(
                geocodes=[_geocode_item("浙江省杭州市上城区杭州东站", HANGZHOU_EAST)]
            ),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[
                    _geocode_item(
                        "浙江省杭州市西湖区龙翔桥地铁站",
                        LONGXIANGQIAO,
                        level="公交地铁站点",
                    )
                ]
            ),
        },
        {
            2000: _ok(
                pois=[
                    {
                        "name": "某咖啡店 B",
                        "address": "示例路 8 号",
                        "location": "120.190,30.280",
                        "distance": "420",
                    },
                    {
                        "name": "某咖啡店 A",
                        "address": "示例路 1 号",
                        "location": "120.186,30.275",
                        "distance": "186",
                    },
                    {
                        "name": "某咖啡店 C",
                        "address": "示例巷 12 号",
                        "location": "120.200,30.285",
                        "distance": "910",
                    },
                ]
            )
        },
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    data = response.json()["data"]
    assert SEARCH_ID_PATTERN.match(data["search_id"])
    assert data["midpoint"]["longitude"] == (120.212010 + 120.161000) / 2
    assert data["midpoint"]["latitude"] == (30.290800 + 30.259000) / 2
    assert [poi["name"] for poi in data["pois"]] == ["某咖啡店 A", "某咖啡店 B", "某咖啡店 C"]
    assert data["pois"][0]["distance_to_midpoint_m"] == 186
    location = handler.around_calls[0]["location"]
    lng, lat = location.split(",")
    assert float(lng) == round(data["midpoint"]["longitude"], 6)
    assert float(lat) == round(data["midpoint"]["latitude"], 6)
    assert handler.around_calls[0]["citylimit"] == "true"
    sidecar = json.loads((tmp_path / "search" / f"{data['search_id']}.json").read_text(encoding="utf-8"))
    assert sidecar["created_at"]
    assert sidecar["search_id"] == data["search_id"]
    assert sidecar["radius_m"] == 2000


def test_search_expands_radius_when_first_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    handler = RecordingHandler(
        {
            "杭州东站": _ok(geocodes=[_geocode_item("浙江省杭州市上城区杭州东站", HANGZHOU_EAST)]),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[_geocode_item("浙江省杭州市西湖区龙翔桥地铁站", LONGXIANGQIAO)]
            ),
        },
        {
            2000: _ok(pois=[]),
            5000: _ok(
                pois=[
                    {
                        "name": "远处咖啡店",
                        "address": "示例大道 9 号",
                        "location": "120.186,30.275",
                        "distance": "3200",
                    }
                ]
            ),
        },
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    assert [call["radius"] for call in handler.around_calls] == [2000, 5000]
    sidecar = json.loads(
        (tmp_path / "search" / f"{response.json()['data']['search_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert sidecar["radius_m"] == 5000


def test_search_no_poi(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    handler = RecordingHandler(
        {
            "杭州东站": _ok(geocodes=[_geocode_item("浙江省杭州市上城区杭州东站", HANGZHOU_EAST)]),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[_geocode_item("浙江省杭州市西湖区龙翔桥地铁站", LONGXIANGQIAO)]
            ),
        },
        {2000: _ok(pois=[]), 5000: _ok(pois=[])},
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "NO_POI"
    assert error["stage"] == "search"
    assert not (tmp_path / "search").exists()


def test_search_location_ambiguous(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    handler = RecordingHandler(
        {
            "杭州东站": _ok(
                geocodes=[
                    _geocode_item(
                        "浙江省杭州市上城区杭州东站东广场",
                        "120.2120,30.2908",
                        name="杭州东站东广场",
                    ),
                    _geocode_item(
                        "浙江省杭州市上城区杭州东站西广场",
                        "120.2140,30.2908",
                        name="杭州东站西广场",
                    ),
                ]
            ),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[_geocode_item("浙江省杭州市西湖区龙翔桥地铁站", LONGXIANGQIAO)]
            ),
        },
        {2000: _ok(pois=[])},
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LOCATION_AMBIGUOUS"
    assert handler.around_calls == []


def test_search_retries_around_without_citylimit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)

    class Handler(RecordingHandler):
        async def get(self, url, params=None):
            params = params or {}
            if "geocode" in url:
                self.geo_calls.append(params)
                return FakeResponse(self.geo_by_address[params.get("address")])
            self.around_calls.append(params)
            if params.get("citylimit") == "true":
                return FakeResponse(
                    {
                        "status": "0",
                        "infocode": "30001",
                        "info": "ENGINE_RESPONSE_DATA_ERROR",
                    }
                )
            return FakeResponse(self.around_by_radius[int(params["radius"])])

    handler = Handler(
        {
            "杭州东站": _ok(geocodes=[_geocode_item("浙江省杭州市上城区杭州东站", HANGZHOU_EAST)]),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[_geocode_item("浙江省杭州市西湖区龙翔桥地铁站", LONGXIANGQIAO)]
            ),
        },
        {
            2000: _ok(
                pois=[
                    {
                        "name": "某咖啡店",
                        "address": "示例路 1 号",
                        "location": "120.186,30.275",
                        "distance": "186",
                    }
                ]
            )
        },
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    assert handler.around_calls[0]["citylimit"] == "true"
    assert "citylimit" not in handler.around_calls[1]
    assert response.json()["data"]["pois"][0]["name"] == "某咖啡店"


def test_search_retries_geocode_without_city(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)

    class Handler(RecordingHandler):
        async def get(self, url, params=None):
            params = params or {}
            if "geocode" in url:
                self.geo_calls.append(params)
                if params.get("city"):
                    return FakeResponse(
                        {
                            "status": "0",
                            "infocode": "30001",
                            "info": "ENGINE_RESPONSE_DATA_ERROR",
                        }
                    )
                address = params.get("address", "")
                for key, payload in self.geo_by_address.items():
                    if key in address:
                        return FakeResponse(payload)
                raise AssertionError(f"unexpected address {address}")
            self.around_calls.append(params)
            return FakeResponse(self.around_by_radius[int(params["radius"])])

    handler = Handler(
        {
            "杭州东站": _ok(geocodes=[_geocode_item("浙江省杭州市上城区杭州东站", HANGZHOU_EAST)]),
            "西湖龙翔桥地铁站": _ok(
                geocodes=[_geocode_item("浙江省杭州市西湖区龙翔桥地铁站", LONGXIANGQIAO)]
            ),
        },
        {
            2000: _ok(
                pois=[
                    {
                        "name": "某咖啡店",
                        "address": "示例路 1 号",
                        "location": "120.186,30.275",
                        "distance": "186",
                    }
                ]
            )
        },
    )
    _install_amap(monkeypatch, handler)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 200
    assert any("city" in call for call in handler.geo_calls)
    assert any("city" not in call for call in handler.geo_calls)


def test_search_missing_field():
    response = client.post("/search", json={"city_a": "杭州"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["stage"] == "search"


def test_search_missing_api_key_does_not_call_network(monkeypatch):
    monkeypatch.setattr(settings, "amap_api_key", "")
    with patch("services.search_places.httpx.AsyncClient") as client_cls:
        response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
    client_cls.assert_not_called()


def test_search_upstream_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "amap_api_key", "test-key")

    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("services.search_places.httpx.AsyncClient", TimeoutClient)
    response = client.post("/search", json=SEARCH_BODY)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"
