from __future__ import annotations

import logging

import httpx

from config import settings
from services.http_ipv4 import ipv4_transport

logger = logging.getLogger(__name__)
STAGE = "finalize"
TTS_DEGRADE = "语音合成失败，已为你保留文字推荐。"
DOWNLOAD_DEGRADE = "语音下载失败，已为你保留文字推荐。"


def _extract_audio_url(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("code"):
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR call=tts provider_code=%s",
            STAGE,
            payload.get("code"),
        )
        return None
    output = payload.get("output")
    if not isinstance(output, dict):
        return None
    audio = output.get("audio")
    if not isinstance(audio, dict):
        return None
    url = audio.get("url")
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    return url


async def synthesize_url(text: str) -> str | None:
    if not settings.bailian_api_key.strip():
        logger.info("stage=%s warning=tts_missing_key", STAGE)
        return None
    timeout = httpx.Timeout(settings.tts_timeout_seconds, connect=5.0)
    body = {
        "model": settings.bailian_tts_model,
        "input": {
            "text": text,
            "voice": settings.bailian_tts_voice,
            "language_type": "Chinese",
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.bailian_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout, transport=ipv4_transport()
        ) as client:
            response = await client.post(
                settings.bailian_tts_url,
                headers=headers,
                json=body,
            )
    except httpx.TimeoutException:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT call=tts", STAGE)
        return None
    except httpx.HTTPError:
        logger.info("stage=%s error_code=UPSTREAM_ERROR call=tts_http", STAGE)
        return None
    if response.status_code != 200:
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR http_status=%s call=tts",
            STAGE,
            response.status_code,
        )
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return _extract_audio_url(payload)


async def download_audio(url: str) -> bytes | None:
    timeout = httpx.Timeout(settings.tts_download_timeout_seconds, connect=5.0)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=ipv4_transport(),
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        logger.info("stage=%s error_code=UPSTREAM_TIMEOUT call=tts_download", STAGE)
        return None
    except httpx.HTTPError:
        logger.info("stage=%s error_code=UPSTREAM_ERROR call=tts_download", STAGE)
        return None
    if response.status_code != 200:
        logger.info(
            "stage=%s error_code=UPSTREAM_ERROR http_status=%s call=tts_download",
            STAGE,
            response.status_code,
        )
        return None
    data = response.content
    if not data:
        return None
    logger.info("stage=%s call=tts_download bytes=%s", STAGE, len(data))
    return data
