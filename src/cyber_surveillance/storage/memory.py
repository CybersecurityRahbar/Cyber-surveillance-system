from collections import deque

from cyber_surveillance.detection.models import SecurityAlert
from cyber_surveillance.domain.events import SecurityEvent


class InMemoryStore:
    """Bounded development/test store. Data is intentionally not durable."""

    def __init__(self, max_events: int = 10_000) -> None:
        if max_events < 100:
            raise ValueError("max_events must be >= 100")
        self._events: deque[SecurityEvent] = deque(maxlen=max_events)
        self._event_ids: set[str] = set()
        self._alerts: deque[SecurityAlert] = deque(maxlen=max_events)

    def add_event(self, event: SecurityEvent) -> bool:
        if event.event_id in self._event_ids:
            return False
        if len(self._events) == self._events.maxlen:
            oldest = self._events[0]
            self._event_ids.discard(oldest.event_id)
        self._events.append(event)
        self._event_ids.add(event.event_id)
        return True

    def add_alert(self, alert: SecurityAlert) -> None:
        self._alerts.append(alert)

    def recent_events(self, limit: int = 100) -> list[SecurityEvent]:
        return list(reversed(list(self._events)[-limit:]))

    def recent_alerts(self, limit: int = 100) -> list[SecurityAlert]:
        return list(reversed(list(self._alerts)[-limit:]))

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def alert_count(self) -> int:
        return len(self._alerts)
