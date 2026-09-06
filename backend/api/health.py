from fastapi import APIRouter, Request

from schemas import HealthData, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        request_id=request.state.request_id,
        data=HealthData(status="ok"),
    )
