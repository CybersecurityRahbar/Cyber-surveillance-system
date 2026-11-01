import asyncio
from dataclasses import dataclass

from cyber_surveillance.detection.engine import DetectionEngine
from cyber_surveillance.detection.models import SecurityAlert
from cyber_surveillance.detection.rules import AuthenticationFailureBurstRule
from cyber_surveillance.domain.events import SecurityEvent
from cyber_surveillance.storage.memory import InMemoryStore


@dataclass(frozen=True)
class IngestSummary:
    accepted: int
    duplicates: int
    alerts_created: int


class MonitorRuntime:
    """Coordinates ingestion, idempotency, storage and rule execution."""

    def __init__(self, max_events: int, threshold: int, window_seconds: int) -> None:
        self.store = InMemoryStore(max_events=max_events)
        self.engine = DetectionEngine(
            rules=[
                AuthenticationFailureBurstRule(
                    threshold=threshold,
                    window_seconds=window_seconds,
                )
            ]
        )
        self._lock = asyncio.Lock()

    async def ingest(self, events: list[SecurityEvent]) -> IngestSummary:
        accepted = 0
        duplicates = 0
        alerts_created = 0
        async with self._lock:
            for event in events:
                if not self.store.add_event(event):
                    duplicates += 1
                    continue
                accepted += 1
                alerts: list[SecurityAlert] = self.engine.process(event)
                for alert in alerts:
                    self.store.add_alert(alert)
                    alerts_created += 1
        return IngestSummary(
            accepted=accepted,
            duplicates=duplicates,
            alerts_created=alerts_created,
        )
