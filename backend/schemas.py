from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: str = Field(examples=["ok"])


class HealthResponse(BaseModel):
    request_id: str
    data: HealthData


class UploadData(BaseModel):
    audio_id: str = Field(examples=["rec_7c2e9a0b-4d11-4c8a-9f21-0b1c2d3e4f5a"])


class UploadResponse(BaseModel):
    request_id: str
    data: UploadData


class ErrorDetail(BaseModel):
    code: str
    message: str
    stage: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail
