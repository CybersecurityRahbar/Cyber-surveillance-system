from collections import defaultdict, deque
from dataclasses import dataclass

from traffic_surveillance.domain.models import TimestampQuality
from traffic_surveillance.vision.calibration import HomographyProjector


@dataclass(frozen=True)
class SpeedMeasurement:
    track_id: int
    speed_kmh: float
    raw_speed_kmh: float
    valid_for_enforcement: bool
    timestamp_quality: TimestampQuality


class SpeedEstimator:
    """Estimate ground-plane speed from a tracked vehicle's road-contact point."""

    def __init__(
        self,
        projector: HomographyProjector,
        *,
        median_window: int = 5,
        calibration_verified: bool = False,
        max_gap_seconds: float = 2.0,
    ) -> None:
        if median_window < 1:
            raise ValueError("median_window must be positive.")
        if max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be positive.")
        self.projector = projector
        self.calibration_verified = calibration_verified
        self.max_gap_seconds = max_gap_seconds
        self._previous: dict[
            int, tuple[float, float, float, TimestampQuality]
        ] = {}
        self._speeds: dict[int, deque[float]] = defaultdict(
            lambda: deque(maxlen=median_window)
        )

    def update(
        self,
        track_id: int,
        image_point: tuple[float, float],
        timestamp_seconds: float,
        timestamp_quality: TimestampQuality,
    ) -> SpeedMeasurement | None:
        ground = self.projector.project(image_point)
        current = (timestamp_seconds, ground.x_m, ground.y_m, timestamp_quality)
        previous = self._previous.get(track_id)
        self._previous[track_id] = current

        if previous is None:
            return None

        delta_time = timestamp_seconds - previous[0]
        if delta_time <= 0 or delta_time > self.max_gap_seconds:
            self._speeds[track_id].clear()
            return None

        distance_m = ((ground.x_m - previous[1]) ** 2 + (ground.y_m - previous[2]) ** 2) ** 0.5
        raw_speed = distance_m / delta_time * 3.6
        self._speeds[track_id].append(raw_speed)
        ordered = sorted(self._speeds[track_id])
        middle = len(ordered) // 2
        if len(ordered) % 2:
            smoothed = ordered[middle]
        else:
            smoothed = (ordered[middle - 1] + ordered[middle]) / 2.0

        valid = (
            self.calibration_verified
            and timestamp_quality == TimestampQuality.SOURCE_PTS
            and previous[3] == TimestampQuality.SOURCE_PTS
        )
        return SpeedMeasurement(
            track_id=track_id,
            speed_kmh=smoothed,
            raw_speed_kmh=raw_speed,
            valid_for_enforcement=valid,
            timestamp_quality=timestamp_quality,
        )

    def forget_track(self, track_id: int) -> None:
        self._previous.pop(track_id, None)
        self._speeds.pop(track_id, None)
