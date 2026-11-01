from datetime import datetime

from traffic_surveillance.analytics.speed import SpeedMeasurement
from traffic_surveillance.domain.models import EventType, Severity, SurveillanceEvent


def evaluate_speed_limit(
    *,
    camera_id: str,
    track_id: int,
    measurement: SpeedMeasurement,
    speed_limit_kmh: float,
    occurred_at: datetime,
    tolerance_kmh: float = 2.0,
) -> SurveillanceEvent | None:
    """Create an over-speed event only from a verified metric/timing measurement."""
    if speed_limit_kmh <= 0 or tolerance_kmh < 0:
        raise ValueError("Speed limit must be positive and tolerance cannot be negative.")
    if not measurement.valid_for_enforcement:
        return None
    if measurement.speed_kmh <= speed_limit_kmh + tolerance_kmh:
        return None

    return SurveillanceEvent(
        camera_id=camera_id,
        event_type=EventType.SPEEDING,
        severity=Severity.HIGH,
        occurred_at=occurred_at,
        title="Vehicle exceeded configured speed limit",
        description=(
            f"Measured {measurement.speed_kmh:.1f} km/h against "
            f"a limit of {speed_limit_kmh:.1f} km/h."
        ),
        track_id=track_id,
        confidence=1.0,
        evidence={
            "speed_kmh": round(measurement.speed_kmh, 2),
            "raw_speed_kmh": round(measurement.raw_speed_kmh, 2),
            "speed_limit_kmh": speed_limit_kmh,
            "timestamp_quality": measurement.timestamp_quality.value,
        },
    )
