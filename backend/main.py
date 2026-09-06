import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import api_router
from config import settings
from errors import AppError
from schemas import ErrorDetail, ErrorResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(
    title="语音约碰面地点",
    version="0.1.0",
    description="当前提供健康检查、录音上传、语音识别、信息提取、碰面搜店、推荐语与语音播报。",
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _stage_from_path(path: str) -> str:
    stripped = path.rstrip("/")
    if "/audio/" in path or stripped.endswith("/audio"):
        return "audio"
    if stripped.endswith("/finalize"):
        return "finalize"
    if stripped.endswith("/search"):
        return "search"
    if stripped.endswith("/extract"):
        return "extract"
    if stripped.endswith("/asr"):
        return "asr"
    if stripped.endswith("/upload"):
        return "upload"
    if stripped.endswith("/health"):
        return "health"
    return "upload"


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    body = ErrorResponse(
        request_id=_request_id(request),
        error=ErrorDetail(code=exc.code, message=exc.message, stage=exc.stage),
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    body = ErrorResponse(
        request_id=_request_id(request),
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="请求缺少字段或字段类型不正确。",
            stage=_stage_from_path(request.url.path),
        ),
    )
    return JSONResponse(status_code=422, content=body.model_dump())


app.include_router(api_router)
