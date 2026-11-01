from bisect import insort
from datetime import datetime, timedelta
from hashlib import sha256

from cyber_surveillance.detection.models import SecurityAlert
from cyber_surveillance.domain.events import (
    EventCategory,
    EventOutcome,
    SecurityEvent,
    Severity,
)


class AuthenticationFailureBurstRule:
    """Detect repeated authentication failures for one user from one source IP."""

    rule_id = "auth.failure_burst"
    version = "1.0.0"

    def __init__(self, threshold: int = 5, window_seconds: int = 300) -> None:
        if threshold < 2:
            raise ValueError("threshold must be >= 2")
        if window_seconds < 10:
            raise ValueError("window_seconds must be >= 10")
        self.threshold = threshold
        self.window = timedelta(seconds=window_seconds)
        self._events: dict[tuple[str, str, str], list[tuple[datetime, str, str]]] = {}
        self._watermarks: dict[tuple[str, str, str], datetime] = {}
        self._active: set[tuple[str, str, str]] = set()

    def evaluate(self, event: SecurityEvent) -> SecurityAlert | None:
        if (
            event.category != EventCategory.AUTHENTICATION
            or event.outcome != EventOutcome.FAILURE
            or event.src_ip is None
            or not event.principal
        ):
            return None

        source_ip = str(event.src_ip)
        key = (event.tenant_id, event.principal.casefold(), source_ip)
        watermark = max(self._watermarks.get(key, event.event_time), event.event_time)
        self._watermarks[key] = watermark

        bucket = self._events.setdefault(key, [])
        insort(bucket, (event.event_time, event.event_id, event.sensor_id))
        cutoff = watermark - self.window
        while bucket and bucket[0][0] < cutoff:
            bucket.pop(0)

        if event.event_time < cutoff:
            return None

        if len(bucket) < self.threshold:
            self._active.discard(key)
            return None

        if key in self._active:
            return None

        self._active.add(key)
        matching = bucket[-self.threshold :]
        event_ids = [item[1] for item in matching]
        first_seen = matching[0][0]
        last_seen = matching[-1][0]
        fingerprint_material = "|".join((self.rule_id, *key, first_seen.isoformat()))
        fingerprint = sha256(fingerprint_material.encode("utf-8")).hexdigest()

        severity = Severity.CRITICAL if len(bucket) >= self.threshold * 2 else Severity.HIGH
        return SecurityAlert(
            fingerprint=fingerprint,
            rule_id=self.rule_id,
            rule_version=self.version,
            title="Repeated authentication failures",
            description=(
                f"{len(bucket)} authentication failures for account {event.principal} "
                f"from {source_ip} within {int(self.window.total_seconds())} seconds."
            ),
            severity=severity,
            first_seen=first_seen,
            last_seen=last_seen,
            tenant_id=event.tenant_id,
            sensor_ids=sorted({item[2] for item in matching}),
            event_ids=event_ids,
            entities={"principal": event.principal, "source_ip": source_ip},
            evidence={
                "failure_count": len(bucket),
                "threshold": self.threshold,
                "window_seconds": int(self.window.total_seconds()),
            },
            attack_techniques=["T1110"],
        )
