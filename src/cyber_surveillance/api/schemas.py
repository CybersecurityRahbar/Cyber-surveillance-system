from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=160)
    tenant_id: str = Field(default="default", min_length=1, max_length=128)
    source_type: str | None = Field(default=None, max_length=80)
    events: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    duplicates: int
    alerts_created: int


class RuntimeStatus(BaseModel):
    service: str
    environment: str
    storage: str
    durable_storage: bool
    events_in_memory: int
    alerts_in_memory: int
