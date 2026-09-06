from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from errors import AppError
from main import app
from services import storage

client = TestClient(app)


def _store_audio(tmp_path: Path, monkeypatch, content: bytes = b"fake-webm") -> str:
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    audio_id = storage.new_audio_id()
    part = tmp_path / "audio"
    part.mkdir(parents=True, exist_ok=True)
    source = part / f"{audio_id}.part"
    source.write_bytes(content)
    storage.commit_audio(
        audio_id=audio_id,
        source_path=source,
        content_type="audio/webm",
        container="webm",
        codec="opus",
        duration_sec=3.0,
        size_bytes=len(content),
    )
    return audio_id


def test_asr_success(tmp_path: Path, monkeypatch):
    audio_id = _store_audio(tmp_path, monkeypatch)
    with patch("api.asr.transcribe", new=AsyncMock(return_value="我在杭州东站。")):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["text"] == "我在杭州东站。"
    assert body["request_id"]


def test_asr_audio_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_dir", tmp_path)
    response = client.post(
        "/asr",
        json={"audio_id": "rec_11111111-1111-1111-1111-111111111111"},
    )
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "AUDIO_ID_NOT_FOUND"
    assert error["stage"] == "asr"


def test_asr_empty_transcript(tmp_path: Path, monkeypatch):
    audio_id = _store_audio(tmp_path, monkeypatch)
    with patch(
        "api.asr.transcribe",
        new=AsyncMock(
            side_effect=AppError(422, "ASR_EMPTY", "没有识别出有效文字，请重新录音。", "asr")
        ),
    ):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ASR_EMPTY"


def test_asr_timeout(tmp_path: Path, monkeypatch):
    audio_id = _store_audio(tmp_path, monkeypatch)
    with patch(
        "api.asr.transcribe",
        new=AsyncMock(
            side_effect=AppError(504, "UPSTREAM_TIMEOUT", "语音识别超时，请稍后重试。", "asr")
        ),
    ):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"


def test_asr_upstream_error(tmp_path: Path, monkeypatch):
    audio_id = _store_audio(tmp_path, monkeypatch)
    with patch(
        "api.asr.transcribe",
        new=AsyncMock(
            side_effect=AppError(502, "UPSTREAM_ERROR", "语音识别暂时失败，请稍后重试。", "asr")
        ),
    ):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_asr_missing_field():
    response = client.post("/asr", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_asr_missing_api_key_does_not_call_network(tmp_path: Path, monkeypatch):
    audio_id = _store_audio(tmp_path, monkeypatch)
    monkeypatch.setattr("services.bailian_asr.settings.bailian_api_key", "")
    with patch("services.bailian_asr.httpx.AsyncClient") as client_cls:
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
    client_cls.assert_not_called()


def test_transcribe_parses_dashscope_message(monkeypatch):
    from services import bailian_asr

    monkeypatch.setattr(bailian_asr.settings, "bailian_api_key", "test-key")
    monkeypatch.setattr(bailian_asr.settings, "max_asr_base64_bytes", 1024)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "output": {
                    "choices": [
                        {"message": {"content": [{"text": "  西湖龙翔桥。"}]}}
                    ]
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            assert "Authorization" in kwargs["headers"]
            audio = kwargs["json"]["input"]["messages"][0]["content"][0]["audio"]
            assert audio.startswith("data:audio/webm;base64,")
            return FakeResponse()

    monkeypatch.setattr(bailian_asr.httpx, "AsyncClient", FakeAsyncClient)

    import asyncio

    text = asyncio.run(bailian_asr.transcribe(b"abc", "audio/webm"))
    assert text == "西湖龙翔桥。"


def test_transcribe_timeout(monkeypatch):
    from services import bailian_asr

    monkeypatch.setattr(bailian_asr.settings, "bailian_api_key", "test-key")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(bailian_asr.httpx, "AsyncClient", FakeAsyncClient)

    import asyncio

    try:
        asyncio.run(bailian_asr.transcribe(b"abc", "audio/webm"))
        raise AssertionError("timeout should raise")
    except AppError as exc:
        assert exc.status_code == 504
        assert exc.code == "UPSTREAM_TIMEOUT"
