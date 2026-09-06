from __future__ import annotations

import logging

from errors import AppError
from services.audio_format import sniff_audio
from services.bailian_tts import (
    DOWNLOAD_DEGRADE,
    TTS_DEGRADE,
    download_audio,
    synthesize_url,
)
from services.recommend import generate_reply
from services.search_store import get_search
from services.tts_store import commit_tts, new_tts_id, public_audio_url

logger = logging.getLogger(__name__)
STAGE = "finalize"


def _first_poi(payload: dict) -> tuple[str, str, int]:
    pois = payload.get("pois")
    if not isinstance(pois, list) or not pois:
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", STAGE)
    first = pois[0]
    if not isinstance(first, dict):
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", STAGE)
    name = first.get("name")
    address = first.get("address")
    distance = first.get("distance_to_midpoint_m")
    if not isinstance(name, str) or not name.strip():
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", STAGE)
    if not isinstance(address, str) or not address.strip():
        raise AppError(404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", STAGE)
    if not isinstance(distance, int):
        try:
            distance = int(distance)
        except (TypeError, ValueError) as exc:
            raise AppError(
                404, "SEARCH_ID_NOT_FOUND", "查询编号不存在或已过期。", STAGE
            ) from exc
    return name.strip(), address.strip(), distance


async def finalize_meeting(search_id: str) -> tuple[str, str | None, str | None]:
    payload = get_search(search_id)
    shop_name, shop_address, distance_m = _first_poi(payload)
    reply_text = await generate_reply(
        city_a=str(payload.get("city_a") or ""),
        address_a=str(payload.get("address_a") or ""),
        city_b=str(payload.get("city_b") or ""),
        address_b=str(payload.get("address_b") or ""),
        category=str(payload.get("category") or "咖啡店"),
        shop_name=shop_name,
        shop_address=shop_address,
        distance_m=distance_m,
    )

    audio_url_remote = await synthesize_url(reply_text)
    if not audio_url_remote:
        return reply_text, None, TTS_DEGRADE

    audio_bytes = await download_audio(audio_url_remote)
    if not audio_bytes:
        return reply_text, None, DOWNLOAD_DEGRADE

    try:
        extension, content_type = sniff_audio(audio_bytes)
    except ValueError:
        logger.info("stage=%s warning=unrecognized_audio_bytes", STAGE)
        return reply_text, None, DOWNLOAD_DEGRADE

    stored = commit_tts(
        audio_id=new_tts_id(),
        data=audio_bytes,
        extension=extension,
        content_type=content_type,
    )
    logger.info(
        "stage=%s search_id=%s audio_id=%s content_type=%s bytes=%s",
        STAGE,
        search_id,
        stored.audio_id,
        stored.content_type,
        len(audio_bytes),
    )
    return reply_text, public_audio_url(stored.audio_id), None
