from datetime import datetime, timedelta, timezone

from cyber_surveillance.detection.rules import AuthenticationFailureBurstRule
from cyber_surveillance.domain.events import (
    EventCategory,
    EventOutcome,
    EventSource,
    SecurityEvent,
    Severity,
)


def make_event(index: int, when: datetime) -> SecurityEvent:
    return SecurityEvent(
        event_id=f"auth-{index}",
        event_time=when,
        sensor_id="auth-sensor",
        source_type=EventSource.SYSLOG,
        category=EventCategory.AUTHENTICATION,
        action="login",
        outcome=EventOutcome.FAILURE,
        severity=Severity.MEDIUM,
        principal="analyst",
        src_ip="192.0.2.10",
    )


def test_detects_failure_burst_once_and_resets_after_window_expires() -> None:
    rule = AuthenticationFailureBurstRule(threshold=3, window_seconds=60)
    start = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)

    assert rule.evaluate(make_event(1, start)) is None
    assert rule.evaluate(make_event(2, start + timedelta(seconds=5))) is None

    alert = rule.evaluate(make_event(3, start + timedelta(seconds=10)))
    assert alert is not None
    assert alert.rule_id == "auth.failure_burst"
    assert len(alert.event_ids) == 3
    assert alert.attack_techniques == ["T1110"]

    assert rule.evaluate(make_event(4, start + timedelta(seconds=15))) is None
    assert rule.evaluate(make_event(5, start + timedelta(seconds=120))) is None
    assert rule.evaluate(make_event(6, start + timedelta(seconds=125))) is None
    assert rule.evaluate(make_event(7, start + timedelta(seconds=130))) is not None


def test_ignores_late_event_outside_current_watermark_window() -> None:
    rule = AuthenticationFailureBurstRule(threshold=2, window_seconds=30)
    start = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)

    assert rule.evaluate(make_event(1, start)) is None
    assert rule.evaluate(make_event(2, start + timedelta(seconds=100))) is None
    assert rule.evaluate(make_event(3, start + timedelta(seconds=5))) is None
