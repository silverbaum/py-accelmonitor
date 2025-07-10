from pydantic import BaseModel
from datetime import datetime


class Tag(BaseModel):
    mac: str
    temperature: float
    humidity: float
    pressure: float
    acceleration_x: float
    acceleration_y: float
    acceleration_z: float


class GatewayData(BaseModel):
    gwmac: str
    tags: dict[str, Tag]


class GatewayHTTPRequest(BaseModel):
    data: GatewayData


class Video(BaseModel):
    name: str
    start_timestamp: datetime
    video_duration: str
    video_path: str
