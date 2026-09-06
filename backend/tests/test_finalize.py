import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from config import settings
from main import app
from services.audio_format import sniff_audio, validate_reply_text
from services.search_store import SEARCH_ID_PATTERN
from services.tts_store import TTS_ID_PATTERN

client = TestClient(app)

SHOP_NAME = "某咖啡店 A"
SHOP_ADDRESS = "示例路 1 号"
REPLY = f"推荐你们在中间附近碰面，可以去{SHOP_ADDRESS}的{SHOP_NAME}，位置大致靠近地理中点。"
WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt "
MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00\xff"


def _write_search(tmp_path: Path, monkeypatch, search_id: str | None = None) -> str:
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    search_id = search_id or "sch_11111111-1111-4111-8111-111111111111"
    folder = tmp_path / "search"
    folder.mkdir(parents=True)
    payload = {
        "search_id": search_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
        "pois": [
            {
                "name": SHOP_NAME,
                "address": SHOP_ADDRESS,
                "distance_to_midpoint_m": 186,
                "longitude": 120.186,
                "latitude": 30.275,
            }
        ],
    }
    (folder / f"{search_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return search_id


def test_sniff_uses_magic_not_suffix():
    assert sniff_audio(WAV_BYTES) == ("wav", "audio/wav")
    assert sniff_audio(MP3_BYTES) == ("mp3", "audio/mpeg")


def test_validate_reply_requires_real_shop_fields():
    try:
        validate_reply_text("附近有家不错的店，路上一样久。", SHOP_NAME, SHOP_ADDRESS)
        raise AssertionError("should fail")
    except ValueError:
        pass
    text = validate_reply_text(REPLY, SHOP_NAME, SHOP_ADDRESS)
    assert SHOP_NAME in text
    assert SHOP_ADDRESS in text


def test_validate_reply_accepts_address_without_district_prefix():
    name = "星巴克国贸店"
    address = "北京市朝阳区建国门外大街1号"
    text = validate_reply_text(
        f"推荐去建国门外大街1号的{name}，位置大致靠近地理中点。",
        name,
        address,
    )
    assert name in text


def test_validate_reply_appends_official_address_when_paraphrased():
    text = validate_reply_text(
        f"推荐你们去{SHOP_NAME}碰面，位置大致靠近地理中点。",
        SHOP_NAME,
        SHOP_ADDRESS,
    )
    assert SHOP_NAME in text
    assert SHOP_ADDRESS in text
    assert "地址是" in text


def test_finalize_success_saves_real_wav(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    with (
        patch(
            "services.finalize_meeting.generate_reply",
            new=AsyncMock(return_value=REPLY),
        ),
        patch(
            "services.finalize_meeting.synthesize_url",
            new=AsyncMock(return_value="https://example.invalid/file.mp3"),
        ),
        patch(
            "services.finalize_meeting.download_audio",
            new=AsyncMock(return_value=WAV_BYTES),
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reply_text"] == REPLY
    assert data["warning"] is None
    assert data["audio_url"].startswith("http://localhost:8003/audio/tts_")
    audio_id = data["audio_url"].rsplit("/", 1)[-1]
    assert TTS_ID_PATTERN.match(audio_id)
    wav_path = tmp_path / "tts" / f"{audio_id}.wav"
    assert wav_path.exists()
    assert wav_path.read_bytes().startswith(b"RIFF")
    meta = json.loads((tmp_path / "tts" / f"{audio_id}.json").read_text(encoding="utf-8"))
    assert meta["content_type"] == "audio/wav"
    assert meta["extension"] == "wav"

    audio = client.get(f"/audio/{audio_id}")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content.startswith(b"RIFF")


def test_finalize_keeps_text_when_tts_fails(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    with (
        patch(
            "services.finalize_meeting.generate_reply",
            new=AsyncMock(return_value=REPLY),
        ),
        patch(
            "services.finalize_meeting.synthesize_url",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reply_text"] == REPLY
    assert data["audio_url"] is None
    assert data["warning"]
    assert not list((tmp_path / "tts").glob("tts_*.wav")) if (tmp_path / "tts").exists() else True


def test_finalize_keeps_text_when_download_is_not_audio(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    with (
        patch(
            "services.finalize_meeting.generate_reply",
            new=AsyncMock(return_value=REPLY),
        ),
        patch(
            "services.finalize_meeting.synthesize_url",
            new=AsyncMock(return_value="https://example.invalid/file.wav"),
        ),
        patch(
            "services.finalize_meeting.download_audio",
            new=AsyncMock(return_value=b"not-an-audio-file"),
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reply_text"] == REPLY
    assert data["audio_url"] is None
    assert data["warning"]


def test_finalize_saves_mp3_when_bytes_are_mp3(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    with (
        patch(
            "services.finalize_meeting.generate_reply",
            new=AsyncMock(return_value=REPLY),
        ),
        patch(
            "services.finalize_meeting.synthesize_url",
            new=AsyncMock(return_value="https://example.invalid/file.wav"),
        ),
        patch(
            "services.finalize_meeting.download_audio",
            new=AsyncMock(return_value=MP3_BYTES),
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    audio_id = response.json()["data"]["audio_url"].rsplit("/", 1)[-1]
    assert (tmp_path / "tts" / f"{audio_id}.mp3").exists()
    assert not (tmp_path / "tts" / f"{audio_id}.wav").exists()
    audio = client.get(f"/audio/{audio_id}")
    assert audio.headers["content-type"].startswith("audio/mpeg")


def test_finalize_search_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    response = client.post(
        "/finalize",
        json={"search_id": "sch_11111111-1111-4111-8111-111111111111"},
    )
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "SEARCH_ID_NOT_FOUND"
    assert error["stage"] == "finalize"


def test_finalize_recommend_failure_is_502(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    from errors import AppError

    with patch(
        "services.finalize_meeting.generate_reply",
        new=AsyncMock(
            side_effect=AppError(502, "UPSTREAM_ERROR", "推荐语生成暂时失败，请稍后重试。", "finalize")
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_finalize_invalid_reply_is_502(tmp_path: Path, monkeypatch):
    search_id = _write_search(tmp_path, monkeypatch)
    from errors import AppError

    with patch(
        "services.finalize_meeting.generate_reply",
        new=AsyncMock(
            side_effect=AppError(
                502, "MODEL_OUTPUT_INVALID", "推荐语结果格式异常，请稍后重试。", "finalize"
            )
        ),
    ):
        response = client.post("/finalize", json={"search_id": search_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_OUTPUT_INVALID"


def test_audio_not_found_is_json(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    response = client.get("/audio/tts_11111111-1111-4111-8111-111111111111")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "TTS_AUDIO_NOT_FOUND"
    assert error["stage"] == "audio"
    assert "application/json" in response.headers["content-type"]


def test_finalize_missing_field():
    response = client.post("/finalize", json={})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["stage"] == "finalize"


def test_search_id_pattern():
    assert SEARCH_ID_PATTERN.match("sch_11111111-1111-4111-8111-111111111111")
