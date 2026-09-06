from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from errors import AppError
from main import app
from services.audio_probe import ProbeResult
from services import storage

client = TestClient(app)


def test_upload_success(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    with patch("api.upload.probe_audio", return_value=ProbeResult("webm", "opus", 3.2)):
        response = client.post(
            "/upload",
            files={"file": ("recording.webm", b"fake-webm-bytes", "audio/webm")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["audio_id"].startswith("rec_")
    assert (tmp_path / "audio" / f"{body['data']['audio_id']}.webm").exists()
    assert (tmp_path / "audio" / f"{body['data']['audio_id']}.json").exists()


def test_upload_too_large(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    monkeypatch.setattr("api.upload.settings.max_upload_bytes", 8)
    response = client.post(
        "/upload",
        files={"file": ("recording.webm", b"0123456789", "audio/webm")},
    )
    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "AUDIO_TOO_LARGE"
    assert error["stage"] == "upload"


def test_upload_unsupported_type(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    with patch(
        "api.upload.probe_audio",
        side_effect=AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            "upload",
        ),
    ):
        response = client.post(
            "/upload",
            files={"file": ("note.mp3", b"not-an-audio", "audio/mpeg")},
        )
    assert response.status_code == 415
    error = response.json()["error"]
    assert error["code"] == "AUDIO_UNSUPPORTED_TYPE"


def test_upload_duration_invalid(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    with patch("api.upload.probe_audio", return_value=ProbeResult("webm", "opus", 0.4)):
        response = client.post(
            "/upload",
            files={"file": ("recording.webm", b"fake-webm-bytes", "audio/webm")},
        )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "AUDIO_DURATION_INVALID"


def test_get_audio_expired(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    audio_id = storage.new_audio_id()
    source = tmp_path / "audio"
    source.mkdir(parents=True)
    part = source / f"{audio_id}.part"
    part.write_bytes(b"fake")
    stored = storage.commit_audio(
        audio_id=audio_id,
        source_path=part,
        content_type="audio/webm",
        container="webm",
        codec="opus",
        duration_sec=3.0,
        size_bytes=4,
    )
    expired = datetime.now(timezone.utc) - timedelta(hours=25)
    meta = stored.file_path.with_suffix(".json")
    text = meta.read_text(encoding="utf-8").replace(
        stored.created_at.isoformat(),
        expired.isoformat(),
    )
    meta.write_text(text, encoding="utf-8")
    try:
        storage.get_audio(audio_id)
        raise AssertionError("expired audio should not be readable")
    except AppError as exc:
        assert exc.status_code == 404
        assert exc.code == "AUDIO_ID_NOT_FOUND"
