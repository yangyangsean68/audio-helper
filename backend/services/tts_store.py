from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import settings
from errors import AppError

TTS_ID_PATTERN = re.compile(
    r"^tts_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
STAGE = "audio"


@dataclass(frozen=True)
class StoredTts:
    audio_id: str
    file_path: Path
    content_type: str
    created_at: datetime


def tts_dir() -> Path:
    path = settings.storage_dir / "tts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_tts_id() -> str:
    return f"tts_{uuid.uuid4()}"


def _meta_path(audio_id: str) -> Path:
    return tts_dir() / f"{audio_id}.json"


def _is_expired(created_at: datetime) -> bool:
    return datetime.now(timezone.utc) - created_at > timedelta(hours=settings.audio_ttl_hours)


def commit_tts(*, audio_id: str, data: bytes, extension: str, content_type: str) -> StoredTts:
    created_at = datetime.now(timezone.utc)
    stored_name = f"{audio_id}.{extension}"
    file_path = tts_dir() / stored_name
    file_path.write_bytes(data)
    payload = {
        "audio_id": audio_id,
        "created_at": created_at.isoformat(),
        "stored_name": stored_name,
        "content_type": content_type,
        "size_bytes": len(data),
        "extension": extension,
    }
    _meta_path(audio_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return StoredTts(
        audio_id=audio_id,
        file_path=file_path,
        content_type=content_type,
        created_at=created_at,
    )


def get_tts_audio(audio_id: str) -> StoredTts:
    if not TTS_ID_PATTERN.match(audio_id):
        raise AppError(404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE)
    meta_file = _meta_path(audio_id)
    if not meta_file.exists():
        raise AppError(404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE)
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE
        ) from exc
    if _is_expired(created_at):
        raise AppError(404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE)
    stored_name = payload.get("stored_name")
    if not isinstance(stored_name, str) or Path(stored_name).name != stored_name:
        raise AppError(404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE)
    file_path = tts_dir() / stored_name
    if not file_path.exists():
        raise AppError(404, "TTS_AUDIO_NOT_FOUND", "音频已过期或不存在，请重新生成推荐。", STAGE)
    content_type = str(payload.get("content_type") or "application/octet-stream")
    return StoredTts(
        audio_id=audio_id,
        file_path=file_path,
        content_type=content_type,
        created_at=created_at,
    )


def public_audio_url(audio_id: str) -> str:
    return f"http://localhost:{settings.port}/audio/{audio_id}"
