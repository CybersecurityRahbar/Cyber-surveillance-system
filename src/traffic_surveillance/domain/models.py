from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CameraRole(StrEnum):
    TRAFFIC = "traffic"
    SECURITY = "security"
    MIXED = "mixed"


class EventType(StrEnum):
    SPEEDING = "speeding"
    WRONG_WAY = "wrong_way"
    LINE_CROSSING = "line_crossing"
    STOPPED_VEHICLE = "stopped_vehicle"
    CONGESTION = "congestion"
    ROAD_BLOCKAGE = "road_blockage"
    ZONE_INTRUSION = "zone_intrusion"
    LOITERING = "loitering"
    CROWDING = "crowding"
    UNATTENDED_OBJECT = "unattended_object"
    COLLISION_CANDIDATE = "collision_candidate"
    CAMERA_HEALTH = "camera_health"
    MANUAL_REVIEW = "manual_review"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TimestampQuality(StrEnum):
    SOURCE_PTS = "source_pts"
    ARRIVAL_MONOTONIC = "arrival_monotonic"
    UNKNOWN = "unknown"


class Point2D(BaseModel):
    x: float
    y: float


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def valid_bounds(self) -> "BoundingBox":
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Bounding box must have positive width and height.")
        return self


class Detection(BaseModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    box: BoundingBox
    track_id: int | None = None


class TrackObservation(BaseModel):
    camera_id: str
    track_id: int
    label: str
    foot_point: Point2D
    frame_timestamp_seconds: float
    timestamp_quality: TimestampQuality = TimestampQuality.UNKNOWN


class CameraProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    role: CameraRole = CameraRole.MIXED
    location_label: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    enabled: bool = True


class SurveillanceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    camera_id: str = Field(min_length=1, max_length=128)
    event_type: EventType
    severity: Severity = Severity.INFO
    occurred_at: datetime
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    track_id: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reviewed: bool = False

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamp must be timezone-aware.")
        return value.astimezone(UTC)
