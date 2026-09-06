from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent

CORS_ORIGINS = [
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8003
    cors_origins: list[str] = CORS_ORIGINS

    bailian_api_key: str = ""
    bailian_asr_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    bailian_asr_model: str = "qwen3-asr-flash"
    bailian_tts_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    bailian_tts_model: str = "qwen3-tts-flash"
    bailian_tts_voice: str = "Cherry"

    deepseek_api_key: str = ""
    deepseek_chat_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_model: str = "deepseek-v4-flash"

    amap_api_key: str = ""
    amap_geo_url: str = "https://restapi.amap.com/v3/geocode/geo"
    amap_around_url: str = "https://restapi.amap.com/v3/place/around"

    storage_dir: Path = BACKEND_DIR / "storage"
    audio_ttl_hours: int = 24
    search_timeout_seconds: float = 45.0
    amap_timeout_seconds: float = 12.0
    amap_connect_timeout_seconds: float = 8.0
    max_upload_bytes: int = 5 * 1024 * 1024
    min_audio_seconds: float = 1.0
    max_audio_seconds: float = 60.0
    ffprobe_timeout_seconds: float = 6.0
    asr_timeout_seconds: float = 22.0
    max_asr_base64_bytes: int = 10 * 1024 * 1024
    extract_timeout_seconds: float = 16.0
    recommend_timeout_seconds: float = 10.0
    tts_timeout_seconds: float = 12.0
    tts_download_timeout_seconds: float = 5.0


settings = Settings()
