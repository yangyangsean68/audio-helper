from fastapi import APIRouter

from api.health import router as health_router
from api.upload import router as upload_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(upload_router)
