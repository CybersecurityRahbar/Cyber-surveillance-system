from collections.abc import Sequence


def point_in_polygon(
    point: tuple[float, float],
    polygon: Sequence[tuple[float, float]],
) -> bool:
    """Ray-casting point-in-polygon test; polygon boundary is considered inside."""
    if len(polygon) < 3:
        raise ValueError("A polygon requires at least three points.")

    x, y = point
    inside = False
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]

        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        dot = (x - x1) * (x - x2) + (y - y1) * (y - y2)
        if abs(cross) < 1e-9 and dot <= 1e-9:
            return True

        intersects = (y1 > y) != (y2 > y)
        if intersects:
            x_at_y = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_at_y:
                inside = not inside
    return inside


def signed_side(
    point: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
) -> float:
    return (
        (line_end[0] - line_start[0]) * (point[1] - line_start[1])
        - (line_end[1] - line_start[1]) * (point[0] - line_start[0])
    )
