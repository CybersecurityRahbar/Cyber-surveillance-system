from dataclasses import dataclass

from traffic_surveillance.analytics.geometry import signed_side


@dataclass(frozen=True)
class LineCrossing:
    track_id: int
    direction: str


class DirectedLineCounter:
    """Count each track when it crosses a finite virtual line."""

    def __init__(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        deadband: float = 1e-6,
    ) -> None:
        if start == end:
            raise ValueError("Line endpoints must be different.")
        self.start = start
        self.end = end
        self.deadband = deadband
        self._last_side: dict[int, float] = {}
        self._counted_transition: set[tuple[int, str]] = set()

    def update(self, track_id: int, point: tuple[float, float]) -> LineCrossing | None:
        side = signed_side(point, self.start, self.end)
        previous = self._last_side.get(track_id)
        self._last_side[track_id] = side
        if previous is None or abs(side) <= self.deadband or abs(previous) <= self.deadband:
            return None
        if previous * side >= 0:
            return None

        along_start = (
            (point[0] - self.start[0]) * (self.end[0] - self.start[0])
            + (point[1] - self.start[1]) * (self.end[1] - self.start[1])
        )
        segment_length_sq = (
            (self.end[0] - self.start[0]) ** 2 + (self.end[1] - self.start[1]) ** 2
        )
        if not 0 <= along_start <= segment_length_sq:
            return None

        direction = "negative_to_positive" if previous < 0 < side else "positive_to_negative"
        key = (track_id, direction)
        if key in self._counted_transition:
            return None
        self._counted_transition.add(key)
        return LineCrossing(track_id=track_id, direction=direction)

    def forget_track(self, track_id: int) -> None:
        self._last_side.pop(track_id, None)
        self._counted_transition = {
            item for item in self._counted_transition if item[0] != track_id
        }
