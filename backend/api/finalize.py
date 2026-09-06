import logging
import time

from fastapi import APIRouter, Request

from errors import AppError
from schemas import FinalizeData, FinalizeRequest, FinalizeResponse
from services.finalize_meeting import finalize_meeting

router = APIRouter()
logger = logging.getLogger(__name__)
STAGE = "finalize"


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize(request: Request, payload: FinalizeRequest) -> FinalizeResponse:
    started = time.perf_counter()
    try:
        reply_text, audio_url, warning = await finalize_meeting(payload.search_id)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "stage=%s search_id=%s duration_ms=%s has_audio=%s",
            STAGE,
            payload.search_id,
            elapsed_ms,
            bool(audio_url),
        )
        return FinalizeResponse(
            request_id=request.state.request_id,
            data=FinalizeData(
                reply_text=reply_text,
                audio_url=audio_url,
                warning=warning,
            ),
        )
    except AppError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "stage=%s error_code=%s duration_ms=%s reason=%s",
            exc.stage,
            exc.code,
            elapsed_ms,
            exc.message,
        )
        raise
