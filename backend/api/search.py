import logging
import time

from fastapi import APIRouter, Request

from errors import AppError
from schemas import Midpoint, SearchData, SearchPoi, SearchRequest, SearchResponse
from services.search_places import search_meeting

router = APIRouter()
logger = logging.getLogger(__name__)
STAGE = "search"


@router.post("/search", response_model=SearchResponse)
async def search(request: Request, payload: SearchRequest) -> SearchResponse:
    started = time.perf_counter()
    try:
        stored = await search_meeting(
            payload.city_a,
            payload.address_a,
            payload.city_b,
            payload.address_b,
            payload.category,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "stage=%s search_id=%s duration_ms=%s poi_count=%s",
            STAGE,
            stored.search_id,
            elapsed_ms,
            len(stored.pois),
        )
        return SearchResponse(
            request_id=request.state.request_id,
            data=SearchData(
                search_id=stored.search_id,
                midpoint=Midpoint(
                    longitude=stored.midpoint.longitude,
                    latitude=stored.midpoint.latitude,
                ),
                pois=[
                    SearchPoi(
                        name=poi.name,
                        address=poi.address,
                        distance_to_midpoint_m=poi.distance_to_midpoint_m,
                    )
                    for poi in stored.pois
                ],
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
