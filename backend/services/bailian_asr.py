import base64
import logging
import re

import httpx

from config import settings
from errors import AppError

logger = logging.getLogger(__name__)
STAGE = "asr"
_EMPTY_TEXT = re.compile(r"^[\W_]*$", re.UNICODE)


def _data_uri(mime_type: str, encoded: str) -> str:
    mime = mime_type.split(";", 1)[0].strip() or "audio/webm"
    if mime not in {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg"}:
        mime = "audio/webm"
    return f"data:{mime};base64,{encoded}"


def _is_blank_transcript(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return _EMPTY_TEXT.match(stripped) is not None


def _extract_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)
    output = payload.get("output")
    if not isinstance(output, dict):
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)
    choices = output.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)
    first = choices[0]
    if not isinstance(first, dict):
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)
    message = first.get("message")
    if not isinstance(message, dict):
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts)
    raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE)


async def transcribe(audio_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    if len(encoded) > settings.max_asr_base64_bytes:
        raise AppError(
            413,
            "AUDIO_TOO_LARGE",
            "录音编码后超过识别服务限制，请缩短录音后重试。",
            STAGE,
        )
    if not settings.bailian_api_key.strip():
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务未配置密钥。",
            STAGE,
        )

    headers = {
        "Authorization": f"Bearer {settings.bailian_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.bailian_asr_model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"audio": _data_uri(mime_type, encoded)}],
                }
            ]
        },
        "parameters": {
            "result_format": "message",
            "asr_options": {
                "language": "zh",
                "enable_itn": False,
            },
        },
    }

    timeout = httpx.Timeout(settings.asr_timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                settings.bailian_asr_url,
                headers=headers,
                json=body,
            )
    except httpx.TimeoutException as exc:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT reason=timeout", STAGE)
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "语音识别超时，请稍后重试。",
            STAGE,
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("stage=%s error_code=UPSTREAM_ERROR reason=http_error", STAGE)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别暂时失败，请稍后重试。",
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
            "语音识别暂时失败，请稍后重试。",
            STAGE,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务返回异常。", STAGE) from exc

    dashscope_code = payload.get("code") if isinstance(payload, dict) else None
    if dashscope_code:
        logger.info("stage=%s error_code=UPSTREAM_ERROR provider_code=%s", STAGE, dashscope_code)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别暂时失败，请稍后重试。",
            STAGE,
        )

    text = _extract_text(payload)
    if _is_blank_transcript(text):
        raise AppError(
            422,
            "ASR_EMPTY",
            "没有识别出有效文字，请重新录音。",
            STAGE,
        )
    return text.strip()
