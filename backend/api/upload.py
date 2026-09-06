import asyncio
import logging
import time

from fastapi import APIRouter, File, Request, UploadFile

from config import settings
from errors import AppError
from schemas import UploadData, UploadResponse
from services.audio_probe import probe_audio
from services.storage import audio_dir, commit_audio, new_audio_id

router = APIRouter()
logger = logging.getLogger(__name__)
STAGE = "upload"
CHUNK_SIZE = 64 * 1024


async def _read_limited(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise AppError(
                413,
                "AUDIO_TOO_LARGE",
                "录音文件超过 5MB，请缩短录音后重试。",
                STAGE,
            )
        chunks.append(chunk)
    if total == 0:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )
    return b"".join(chunks)


@router.post("/upload", response_model=UploadResponse)
async def upload(
    request: Request,
    file: UploadFile = File(..., alias="file"),
) -> UploadResponse:
    started = time.perf_counter()
    audio_id = new_audio_id()
    part_path = audio_dir() / f"{audio_id}.part"
    try:
        data = await _read_limited(file)
        part_path.write_bytes(data)
        probe = await asyncio.to_thread(probe_audio, part_path)
        if (
            probe.duration_sec < settings.min_audio_seconds
            or probe.duration_sec > settings.max_audio_seconds
        ):
            raise AppError(
                422,
                "AUDIO_DURATION_INVALID",
                "录音时长需在 1 到 60 秒之间。",
                STAGE,
            )
        stored = commit_audio(
            audio_id=audio_id,
            source_path=part_path,
            content_type=file.content_type or "audio/webm",
            container=probe.container,
            codec=probe.codec,
            duration_sec=probe.duration_sec,
            size_bytes=len(data),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "stage=%s audio_id=%s duration_ms=%s size_bytes=%s duration_sec=%.3f",
            STAGE,
            stored.audio_id,
            elapsed_ms,
            stored.size_bytes,
            stored.duration_sec,
        )
        return UploadResponse(
            request_id=request.state.request_id,
            data=UploadData(audio_id=stored.audio_id),
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
        if part_path.exists():
            part_path.unlink()
        raise
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise
    finally:
        await file.close()
