from __future__ import annotations

import logging

import httpx

from config import BACKEND_DIR, settings
from errors import AppError
from services.audio_format import validate_reply_text
from services.http_ipv4 import ipv4_transport

logger = logging.getLogger(__name__)
STAGE = "finalize"
PROMPT_PATH = BACKEND_DIR / "prompts" / "recommend.txt"


def load_recommend_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_user_message(
    *,
    city_a: str,
    address_a: str,
    city_b: str,
    address_b: str,
    category: str,
    shop_name: str,
    shop_address: str,
    distance_m: int,
) -> str:
    return (
        f"碰面类别：{category}\n"
        f"两人地点：{city_a}{address_a} 与 {city_b}{address_b}\n"
        "只根据下面这一家有效候选写推荐语。\n"
        f"店名：{shop_name}\n"
        f"地址：{shop_address}\n"
        f"距离中点：{distance_m} 米\n"
        "请把上面的店名和地址原样写进推荐语，不要省略地址。\n"
    )


def _content_from_response(payload: object) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务返回异常。", STAGE)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务返回异常。", STAGE)
    first = choices[0]
    if not isinstance(first, dict):
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务返回异常。", STAGE)
    finish_reason = first.get("finish_reason")
    if finish_reason == "length":
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "推荐语结果格式异常，请稍后重试。",
            STAGE,
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务返回异常。", STAGE)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "推荐语结果格式异常，请稍后重试。",
            STAGE,
        )
    return content, str(finish_reason) if finish_reason else None


async def generate_reply(
    *,
    city_a: str,
    address_a: str,
    city_b: str,
    address_b: str,
    category: str,
    shop_name: str,
    shop_address: str,
    distance_m: int,
) -> str:
    if not settings.deepseek_api_key.strip():
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务未配置密钥。", STAGE)

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": load_recommend_prompt()},
            {
                "role": "user",
                "content": build_user_message(
                    city_a=city_a,
                    address_a=address_a,
                    city_b=city_b,
                    address_b=address_b,
                    category=category,
                    shop_name=shop_name,
                    shop_address=shop_address,
                    distance_m=distance_m,
                ),
            },
        ],
        "thinking": {"type": "disabled"},
        "temperature": 0.3,
        "max_tokens": 400,
        "stream": False,
    }
    timeout = httpx.Timeout(settings.recommend_timeout_seconds, connect=5.0)
    try:
        async with httpx.AsyncClient(
            timeout=timeout, transport=ipv4_transport()
        ) as client:
            response = await client.post(
                settings.deepseek_chat_url,
                headers=headers,
                json=body,
            )
    except httpx.TimeoutException as exc:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT reason=recommend_timeout", STAGE)
        raise AppError(504, "UPSTREAM_TIMEOUT", "推荐语生成超时，请稍后重试。", STAGE) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=%s error_code=UPSTREAM_ERROR reason=recommend_http", STAGE)
        raise AppError(502, "UPSTREAM_ERROR", "推荐语生成暂时失败，请稍后重试。", STAGE) from exc

    if response.status_code != 200:
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR http_status=%s call=recommend",
            STAGE,
            response.status_code,
        )
        raise AppError(502, "UPSTREAM_ERROR", "推荐语生成暂时失败，请稍后重试。", STAGE)

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "UPSTREAM_ERROR", "推荐语服务返回异常。", STAGE) from exc

    raw_text, finish_reason = _content_from_response(payload)
    logger.info(
        "stage=%s finish_reason=%s content_chars=%s",
        STAGE,
        finish_reason,
        len(raw_text),
    )
    try:
        checked = validate_reply_text(raw_text, shop_name, shop_address)
    except ValueError as exc:
        logger.info("stage=%s error_code=MODEL_OUTPUT_INVALID reason=%s", STAGE, exc)
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "推荐语结果格式异常，请稍后重试。",
            STAGE,
        ) from exc
    logger.info("stage=%s reply_chars=%s", STAGE, len(checked))
    return checked
