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


class SearchRequest(BaseModel):
    city_a: str = Field(min_length=1, examples=["杭州"])
    address_a: str = Field(min_length=1, examples=["杭州东站"])
    city_b: str = Field(min_length=1, examples=["杭州"])
    address_b: str = Field(min_length=1, examples=["西湖龙翔桥地铁站"])
    category: str = Field(min_length=1, examples=["咖啡店"])


class Midpoint(BaseModel):
    longitude: float = Field(examples=[120.210123])
    latitude: float = Field(examples=[30.274567])


class SearchPoi(BaseModel):
    name: str
    address: str
    distance_to_midpoint_m: int = Field(examples=[186])


class SearchData(BaseModel):
    search_id: str = Field(examples=["sch_9f0a1b2c-3d4e-5f60-7182-93a4b5c6d7e8"])
    midpoint: Midpoint
    pois: list[SearchPoi]


class SearchResponse(BaseModel):
    request_id: str
    data: SearchData


class FinalizeRequest(BaseModel):
    search_id: str = Field(
        min_length=1,
        examples=["sch_9f0a1b2c-3d4e-5f60-7182-93a4b5c6d7e8"],
    )


class FinalizeData(BaseModel):
    reply_text: str
    audio_url: str | None = Field(
        default=None,
        examples=["http://localhost:8003/audio/tts_0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"],
    )
    warning: str | None = None


class FinalizeResponse(BaseModel):
    request_id: str
    data: FinalizeData


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail
