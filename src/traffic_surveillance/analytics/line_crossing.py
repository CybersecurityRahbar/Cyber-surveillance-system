from dataclasses import dataclass

from traffic_surveillance.analytics.geometry import signed_side


@dataclass(frozen=True)
class LineCrossing:
    track_id: int
    direction: str
    intersection: tuple[float, float]


class DirectedLineCounter:
    """Count each observed transition across a finite directed line segment."""

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
        self._last_point: dict[int, tuple[float, float]] = {}

    def update(
        self,
        track_id: int,
        point: tuple[float, float],
    ) -> LineCrossing | None:
        previous = self._last_point.get(track_id)
        self._last_point[track_id] = point
        if previous is None:
            return None

        previous_side = signed_side(previous, self.start, self.end)
        current_side = signed_side(point, self.start, self.end)
        if (
            abs(previous_side) <= self.deadband
            or abs(current_side) <= self.deadband
            or previous_side * current_side >= 0
        ):
            return None

        fraction = previous_side / (previous_side - current_side)
        intersection = (
            previous[0] + fraction * (point[0] - previous[0]),
            previous[1] + fraction * (point[1] - previous[1]),
        )
        line_vector = (self.end[0] - self.start[0], self.end[1] - self.start[1])
        intersection_vector = (
            intersection[0] - self.start[0],
            intersection[1] - self.start[1],
        )
        along = (
            intersection_vector[0] * line_vector[0]
            + intersection_vector[1] * line_vector[1]
        )
        length_squared = line_vector[0] ** 2 + line_vector[1] ** 2
        if not 0 <= along <= length_squared:
            return None

        direction = (
            "negative_to_positive"
            if previous_side < 0 < current_side
            else "positive_to_negative"
        )
        return LineCrossing(
            track_id=track_id,
            direction=direction,
            intersection=intersection,
        )

    def forget_track(self, track_id: int) -> None:
        self._last_point.pop(track_id, None)
