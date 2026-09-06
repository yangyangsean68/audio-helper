import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import settings
from errors import AppError

AUDIO_ID_PATTERN = re.compile(
    r"^rec_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass(frozen=True)
class StoredAudio:
    audio_id: str
    file_path: Path
    created_at: datetime
    duration_sec: float
    size_bytes: int
    content_type: str


def audio_dir() -> Path:
    path = settings.storage_dir / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_audio_id() -> str:
    return f"rec_{uuid.uuid4()}"


def _meta_path(audio_id: str) -> Path:
    return audio_dir() / f"{audio_id}.json"


def _is_expired(created_at: datetime) -> bool:
    return datetime.now(timezone.utc) - created_at > timedelta(hours=settings.audio_ttl_hours)


def commit_audio(
    *,
    audio_id: str,
    source_path: Path,
    content_type: str,
    container: str,
    codec: str,
    duration_sec: float,
    size_bytes: int,
) -> StoredAudio:
    created_at = datetime.now(timezone.utc)
    stored_name = f"{audio_id}.webm"
    file_path = audio_dir() / stored_name
    source_path.replace(file_path)
    payload = {
        "audio_id": audio_id,
        "created_at": created_at.isoformat(),
        "stored_name": stored_name,
        "content_type": content_type,
        "container": container,
        "codec": codec,
        "duration_sec": duration_sec,
        "size_bytes": size_bytes,
    }
    _meta_path(audio_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return StoredAudio(
        audio_id=audio_id,
        file_path=file_path,
        created_at=created_at,
        duration_sec=duration_sec,
        size_bytes=size_bytes,
        content_type=content_type,
    )


def get_audio(audio_id: str) -> StoredAudio:
    """读取临时录音。不存在或超过 24 小时视为无效，供后续 /asr 使用。"""
    if not AUDIO_ID_PATTERN.match(audio_id):
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr")
    meta_file = _meta_path(audio_id)
    if not meta_file.exists():
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr")
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr") from exc

    if _is_expired(created_at):
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr")

    stored_name = payload.get("stored_name")
    if not isinstance(stored_name, str) or Path(stored_name).name != stored_name:
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr")
    file_path = audio_dir() / stored_name
    if not file_path.exists():
        raise AppError(404, "AUDIO_ID_NOT_FOUND", "录音编号不存在或已过期。", "asr")

    return StoredAudio(
        audio_id=audio_id,
        file_path=file_path,
        created_at=created_at,
        duration_sec=float(payload.get("duration_sec") or 0),
        size_bytes=int(payload.get("size_bytes") or 0),
        content_type=str(payload.get("content_type") or "audio/webm"),
    )
