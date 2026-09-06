import logging
import time

from fastapi import APIRouter, Request

from errors import AppError
from schemas import ExtractData, ExtractRequest, ExtractResponse
from services.deepseek_extract import extract_meeting

router = APIRouter()
logger = logging.getLogger(__name__)
STAGE = "extract"


@router.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, payload: ExtractRequest) -> ExtractResponse:
    started = time.perf_counter()
    try:
        result = await extract_meeting(payload.text, payload.city)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("stage=%s duration_ms=%s", STAGE, elapsed_ms)
        return ExtractResponse(
            request_id=request.state.request_id,
            data=ExtractData(
                city_a=result.city_a,
                address_a=result.address_a,
                city_b=result.city_b,
                address_b=result.address_b,
                category=result.category,
            ),
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
        raise
