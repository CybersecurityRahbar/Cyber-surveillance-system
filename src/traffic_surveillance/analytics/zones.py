from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from traffic_surveillance.analytics.geometry import point_in_polygon
from traffic_surveillance.domain.models import EventType, Severity, SurveillanceEvent


class ZoneDefinition(BaseModel):
    zone_id: str
    camera_id: str
    name: str
    polygon: list[tuple[float, float]] = Field(min_length=3)
    loiter_seconds: float | None = Field(default=None, gt=0)
    restricted: bool = True

    @model_validator(mode="after")
    def require_distinct_points(self) -> "ZoneDefinition":
        if len(set(self.polygon)) < 3:
            raise ValueError("A zone must contain at least three distinct points.")
        return self


class ZoneMonitor:
    """Emit entry and one loiter event per continuous visit to a polygon zone."""

    def __init__(self, zone: ZoneDefinition) -> None:
        self.zone = zone
        self._entered: dict[int, datetime] = {}
        self._loitered: set[int] = set()

    def update(
        self,
        track_id: int,
        point: tuple[float, float],
        occurred_at: datetime,
    ) -> list[SurveillanceEvent]:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("Zone event time must be timezone-aware.")
        occurred_at = occurred_at.astimezone(UTC)
        inside = point_in_polygon(point, self.zone.polygon)

        if not inside:
            self._entered.pop(track_id, None)
            self._loitered.discard(track_id)
            return []

        if track_id not in self._entered:
            self._entered[track_id] = occurred_at
            if self.zone.restricted:
                return [
                    SurveillanceEvent(
                        camera_id=self.zone.camera_id,
                        event_type=EventType.ZONE_INTRUSION,
                        severity=Severity.HIGH,
                        occurred_at=occurred_at,
                        title=f"Restricted zone entry: {self.zone.name}",
                        description="A tracked object entered a configured restricted zone.",
                        track_id=track_id,
                        evidence={"zone_id": self.zone.zone_id, "point": point},
                    )
                ]
            return []

        if (
            self.zone.loiter_seconds is None
            or track_id in self._loitered
            or occurred_at - self._entered[track_id] < timedelta(seconds=self.zone.loiter_seconds)
        ):
            return []

        self._loitered.add(track_id)
        return [
            SurveillanceEvent(
                camera_id=self.zone.camera_id,
                event_type=EventType.LOITERING,
                severity=Severity.MEDIUM,
                occurred_at=occurred_at,
                title=f"Loitering in zone: {self.zone.name}",
                description=(
                    "A tracked object remained inside the zone beyond its configured duration."
                ),
                track_id=track_id,
                evidence={
                    "zone_id": self.zone.zone_id,
                    "duration_seconds": (occurred_at - self._entered[track_id]).total_seconds(),
                    "point": point,
                },
            )
        ]

    def forget_track(self, track_id: int) -> None:
        self._entered.pop(track_id, None)
        self._loitered.discard(track_id)
