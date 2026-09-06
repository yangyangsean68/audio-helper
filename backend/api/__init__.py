from fastapi import APIRouter

from api.asr import router as asr_router
from api.audio import router as audio_router
from api.extract import router as extract_router
from api.finalize import router as finalize_router
from api.health import router as health_router
from api.search import router as search_router
from api.upload import router as upload_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(upload_router)
api_router.include_router(asr_router)
api_router.include_router(extract_router)
api_router.include_router(search_router)
api_router.include_router(finalize_router)
api_router.include_router(audio_router)
