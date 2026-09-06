import logging

from fastapi import APIRouter
from fastapi.responses import FileResponse

from services.tts_store import get_tts_audio

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/audio/{audio_id}")
async def download_tts_audio(audio_id: str) -> FileResponse:
    stored = get_tts_audio(audio_id)
    logger.info(
        "stage=audio audio_id=%s content_type=%s",
        stored.audio_id,
        stored.content_type,
    )
    return FileResponse(
        stored.file_path,
        media_type=stored.content_type,
    )
