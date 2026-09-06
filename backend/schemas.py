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


class AsrRequest(BaseModel):
    audio_id: str = Field(examples=["rec_7c2e9a0b-4d11-4c8a-9f21-0b1c2d3e4f5a"])


class AsrData(BaseModel):
    text: str = Field(
        examples=["我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"]
    )


class AsrResponse(BaseModel):
    request_id: str
    data: AsrData


class ExtractRequest(BaseModel):
    text: str = Field(
        min_length=1,
        examples=["我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"],
    )
    city: str = Field(default="杭州", examples=["杭州"])


class ExtractData(BaseModel):
    city_a: str
    address_a: str
    city_b: str
    address_b: str
    category: str


class ExtractResponse(BaseModel):
    request_id: str
    data: ExtractData


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail
