from datetime import UTC, datetime, timedelta

from traffic_surveillance.analytics.geometry import point_in_polygon
from traffic_surveillance.analytics.line_crossing import DirectedLineCounter
from traffic_surveillance.analytics.zones import ZoneDefinition, ZoneMonitor
from traffic_surveillance.domain.models import EventType


def test_point_in_polygon_and_boundary() -> None:
    polygon = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), polygon)
    assert point_in_polygon((0, 5), polygon)
    assert not point_in_polygon((15, 5), polygon)


def test_directed_line_counter_counts_crossing_segment() -> None:
    counter = DirectedLineCounter((0, 0), (10, 0))
    assert counter.update(1, (5, -2)) is None
    crossing = counter.update(1, (5, 2))
    assert crossing is not None
    assert crossing.direction == "negative_to_positive"
    assert counter.update(1, (5, 3)) is None


def test_restricted_zone_entry_and_loitering() -> None:
    zone = ZoneDefinition(
        zone_id="gate-1",
        camera_id="cam-1",
        name="Restricted Gate",
        polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
        loiter_seconds=5,
        restricted=True,
    )
    monitor = ZoneMonitor(zone)
    start = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)

    entry = monitor.update(10, (5, 5), start)
    assert len(entry) == 1
    assert entry[0].event_type == EventType.ZONE_INTRUSION

    assert monitor.update(10, (6, 6), start + timedelta(seconds=4)) == []
    loiter = monitor.update(10, (6, 6), start + timedelta(seconds=6))
    assert len(loiter) == 1
    assert loiter[0].event_type == EventType.LOITERING
    assert monitor.update(10, (6, 6), start + timedelta(seconds=8)) == []
