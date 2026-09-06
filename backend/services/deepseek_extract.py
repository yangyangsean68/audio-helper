import logging

import httpx

from config import BACKEND_DIR, settings
from errors import AppError
from services.http_ipv4 import ipv4_transport
from services.extract_validate import (
    BusinessExtract,
    apply_page_defaults,
    parse_model_json,
    validate_business,
)

logger = logging.getLogger(__name__)
STAGE = "extract"
PROMPT_PATH = BACKEND_DIR / "prompts" / "extract.txt"


def load_extract_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_user_message(text: str, page_city: str) -> str:
    return (
        f"页面选定城市：{page_city.strip() or '杭州'}\n"
        f"用户原话：{text.strip()}\n"
        "请只输出约定 JSON。"
    )


def _content_from_response(payload: object) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务返回异常。", STAGE)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务返回异常。", STAGE)
    first = choices[0]
    if not isinstance(first, dict):
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务返回异常。", STAGE)
    finish_reason = first.get("finish_reason")
    if finish_reason == "length":
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "信息提取结果格式异常，请稍后重试。",
            STAGE,
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务返回异常。", STAGE)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "信息提取结果格式异常，请稍后重试。",
            STAGE,
        )
    return content, str(finish_reason) if finish_reason else None


async def extract_meeting(text: str, page_city: str) -> BusinessExtract:
    if not settings.deepseek_api_key.strip():
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务未配置密钥。",
            STAGE,
        )

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": load_extract_prompt()},
            {"role": "user", "content": build_user_message(text, page_city)},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 800,
        "stream": False,
    }
    timeout = httpx.Timeout(settings.extract_timeout_seconds, connect=5.0)
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
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT reason=timeout", STAGE)
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "信息提取超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=%s error_code=UPSTREAM_ERROR reason=http_error", STAGE)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取暂时失败，请稍后重试。",
            STAGE,
        ) from exc

    if response.status_code != 200:
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR http_status=%s",
            STAGE,
            response.status_code,
        )
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取暂时失败，请稍后重试。",
            STAGE,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务返回异常。", STAGE) from exc

    raw_text, finish_reason = _content_from_response(payload)
    logger.info(
        "stage=%s finish_reason=%s content_chars=%s",
        STAGE,
        finish_reason,
        len(raw_text),
    )
    parsed = parse_model_json(raw_text)
    with_defaults = apply_page_defaults(parsed, page_city)
    return validate_business(with_defaults)
