from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from errors import AppError
from main import app
from services.extract_validate import (
    ModelExtractOutput,
    apply_page_defaults,
    parse_model_json,
    validate_business,
)
from services.extract_validate import BusinessExtract

client = TestClient(app)


def test_parse_model_json_rejects_invalid():
    try:
        parse_model_json("not-json")
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "MODEL_OUTPUT_INVALID"


def test_parse_model_json_rejects_missing_fields():
    try:
        parse_model_json('{"city_a":"杭州"}')
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.code == "MODEL_OUTPUT_INVALID"


def test_validate_complete_hides_diagnostics():
    model = apply_page_defaults(
        ModelExtractOutput(
            city_a="杭州市",
            address_a="杭州东站",
            city_b="杭州",
            address_b="西湖龙翔桥地铁站",
            category=None,
            party_count=2,
            incomplete_reason=None,
        ),
        "杭州",
    )
    result = validate_business(model)
    assert result.category == "咖啡店"
    assert result.city_a == "杭州"
    assert result.city_b == "杭州"


def test_validate_party_count():
    model = ModelExtractOutput(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="龙翔桥",
        category="咖啡店",
        party_count=3,
        incomplete_reason="party_count_not_two",
    )
    try:
        validate_business(model)
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "PARTY_COUNT_INVALID"


def test_validate_vague_address():
    model = ModelExtractOutput(
        city_a="杭州",
        address_a="我家",
        city_b="杭州",
        address_b="杭州东站",
        category="咖啡店",
        party_count=2,
        incomplete_reason="vague_address",
    )
    try:
        validate_business(model)
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.code == "EXTRACT_INCOMPLETE"


def test_validate_cross_city():
    model = ModelExtractOutput(
        city_a="杭州",
        address_a="杭州东站",
        city_b="上海",
        address_b="上海虹桥站",
        category="咖啡店",
        party_count=2,
        incomplete_reason="cross_city",
    )
    try:
        validate_business(model)
        raise AssertionError("should fail")
    except AppError as exc:
        assert exc.code == "CROSS_CITY"


def test_extract_success_returns_five_fields_only():
    result = BusinessExtract(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
    )
    with patch("api.extract.extract_meeting", new=AsyncMock(return_value=result)):
        response = client.post(
            "/extract",
            json={
                "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
                "city": "杭州",
            },
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) == {
        "city_a",
        "address_a",
        "city_b",
        "address_b",
        "category",
    }
    assert "party_count" not in data


def test_extract_missing_text():
    response = client.post("/extract", json={"city": "杭州"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
