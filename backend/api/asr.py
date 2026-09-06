import logging
import time

from fastapi import APIRouter, Request

from errors import AppError
from schemas import AsrData, AsrRequest, AsrResponse
from services.bailian_asr import transcribe
from services.storage import get_audio

router = APIRouter()
logger = logging.getLogger(__name__)
STAGE = "asr"


@router.post("/asr", response_model=AsrResponse)
async def asr(request: Request, payload: AsrRequest) -> AsrResponse:
    started = time.perf_counter()
    try:
        stored = get_audio(payload.audio_id)
        audio_bytes = stored.file_path.read_bytes()
        text = await transcribe(audio_bytes, stored.content_type)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "stage=%s audio_id=%s duration_ms=%s text_chars=%s",
            STAGE,
            stored.audio_id,
            elapsed_ms,
            len(text),
        )
        return AsrResponse(
            request_id=request.state.request_id,
            data=AsrData(text=text),
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
