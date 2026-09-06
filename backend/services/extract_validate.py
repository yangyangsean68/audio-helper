import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from errors import AppError

STAGE = "extract"
VAGUE_ADDRESSES = {"我家", "家", "家里", "公司", "单位", "学校", "这边", "那里", "那儿"}


class ModelExtractOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city_a: str | None
    address_a: str | None
    city_b: str | None
    address_b: str | None
    category: str | None
    party_count: int | None
    incomplete_reason: str | None

    @field_validator("city_a", "address_a", "city_b", "address_b", "category", "incomplete_reason", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value


class BusinessExtract(BaseModel):
    city_a: str
    address_a: str
    city_b: str
    address_b: str
    category: str


def normalize_city(value: str) -> str:
    text = value.strip()
    if text.endswith("市") and len(text) > 1:
        text = text[:-1]
    return text


def _is_vague_address(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip() in VAGUE_ADDRESSES


def parse_model_json(raw: str) -> ModelExtractOutput:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "信息提取结果格式异常，请稍后重试。",
            STAGE,
        ) from exc
    try:
        return ModelExtractOutput.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "信息提取结果格式异常，请稍后重试。",
            STAGE,
        ) from exc


def apply_page_defaults(model: ModelExtractOutput, page_city: str) -> ModelExtractOutput:
    page = page_city.strip() or "杭州"
    category = model.category or "咖啡店"
    return model.model_copy(
        update={
            "city_a": model.city_a or page,
            "city_b": model.city_b or page,
            "category": category,
        }
    )


def validate_business(model: ModelExtractOutput) -> BusinessExtract:
    if model.party_count != 2:
        raise AppError(
            422,
            "PARTY_COUNT_INVALID",
            "当前只支持同一座城市里的两个人，请重新说明两人所在地点。",
            STAGE,
        )

    address_a = None if _is_vague_address(model.address_a) else model.address_a
    address_b = None if _is_vague_address(model.address_b) else model.address_b
    if not address_a or not address_b or not model.city_a or not model.city_b:
        raise AppError(
            422,
            "EXTRACT_INCOMPLETE",
            "地点说得不够清楚，请说明两人所在的具体地点后重试。",
            STAGE,
        )

    city_a = normalize_city(model.city_a)
    city_b = normalize_city(model.city_b)
    if city_a != city_b:
        raise AppError(
            422,
            "CROSS_CITY",
            "当前只支持同一座城市内的两人，请重新表达。",
            STAGE,
        )

    return BusinessExtract(
        city_a=city_a,
        address_a=address_a,
        city_b=city_b,
        address_b=address_b,
        category=model.category or "咖啡店",
    )
