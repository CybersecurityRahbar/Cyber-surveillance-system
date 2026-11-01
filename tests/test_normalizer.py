from datetime import UTC

import pytest

from cyber_surveillance.domain.events import EventCategory, EventOutcome, EventSource, Severity
from cyber_surveillance.ingestion.normalizer import EventNormalizer


def test_normalizes_common_ecs_like_fields_and_keeps_raw_event() -> None:
    raw = {
        "event_id": "evt-1",
        "@timestamp": "2026-11-01T10:00:00Z",
        "event": {
            "category": "authentication",
            "action": "user-login",
            "outcome": "failure",
            "severity": "high",
        },
        "user": {"name": "analyst"},
        "source": {"ip": "192.0.2.10"},
        "host": {"name": "lab-host"},
    }

    event = EventNormalizer().normalize(raw, sensor_id="sensor-1", source_type="syslog")

    assert event.event_id == "evt-1"
    assert event.source_type == EventSource.SYSLOG
    assert event.category == EventCategory.AUTHENTICATION
    assert event.outcome == EventOutcome.FAILURE
    assert event.severity == Severity.HIGH
    assert event.principal == "analyst"
    assert str(event.src_ip) == "192.0.2.10"
    assert event.host == "lab-host"
    assert event.event_time.tzinfo == UTC
    assert event.raw_event == raw


def test_rejects_naive_timestamps() -> None:
    raw = {"timestamp": "2026-11-01T10:00:00", "event_id": "evt-2"}

    with pytest.raises(ValueError, match="timezone"):
        EventNormalizer().normalize(raw, sensor_id="sensor-1")
