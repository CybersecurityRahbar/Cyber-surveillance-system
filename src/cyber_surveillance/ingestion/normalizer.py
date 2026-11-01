from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cyber_surveillance.domain.events import (
    EventCategory,
    EventOutcome,
    EventSource,
    SecurityEvent,
    Severity,
)


def _path(data: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _pick(data: Mapping[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        value = _path(data, path)
        if value is not None and value != "":
            return value
    return default


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, Mapping):
        return None
    text = str(value).strip()
    return text or None


def _parse_time(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000.0
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        parsed = datetime.fromisoformat(candidate)
    else:
        raise ValueError("Unsupported event timestamp format.")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Event timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def _source(value: Any) -> EventSource:
    text = (_as_text(value) or "other").lower().replace("-", "_")
    aliases = {
        "windows": EventSource.WINDOWS_EVENT,
        "wineventlog": EventSource.WINDOWS_EVENT,
        "auditd": EventSource.LINUX_AUDIT,
        "linuxaudit": EventSource.LINUX_AUDIT,
        "unknown": EventSource.OTHER,
    }
    if text in aliases:
        return aliases[text]
    try:
        return EventSource(text)
    except ValueError:
        return EventSource.OTHER


def _category(value: Any) -> EventCategory:
    text = (_as_text(value) or "other").lower().replace("-", "_")
    aliases = {
        "auth": EventCategory.AUTHENTICATION,
        "authentication": EventCategory.AUTHENTICATION,
        "network": EventCategory.NETWORK,
        "connection": EventCategory.NETWORK,
        "process": EventCategory.PROCESS,
        "file": EventCategory.FILE,
        "dns": EventCategory.DNS,
        "tls": EventCategory.TLS,
        "cloud": EventCategory.CLOUD,
        "system": EventCategory.SYSTEM,
    }
    return aliases.get(text, EventCategory.OTHER)


def _outcome(value: Any) -> EventOutcome:
    text = (_as_text(value) or "unknown").lower()
    if text in {"success", "succeeded", "successful", "allowed", "ok"}:
        return EventOutcome.SUCCESS
    if text in {"failure", "failed", "unsuccessful", "denied", "blocked", "error"}:
        return EventOutcome.FAILURE
    return EventOutcome.UNKNOWN


def _severity(value: Any, source: EventSource) -> Severity:
    text = (_as_text(value) or "informational").lower()
    named = {
        "info": Severity.INFORMATIONAL,
        "informational": Severity.INFORMATIONAL,
        "debug": Severity.INFORMATIONAL,
        "notice": Severity.INFORMATIONAL,
        "low": Severity.LOW,
        "warning": Severity.LOW,
        "warn": Severity.LOW,
        "medium": Severity.MEDIUM,
        "moderate": Severity.MEDIUM,
        "high": Severity.HIGH,
        "error": Severity.HIGH,
        "critical": Severity.CRITICAL,
        "fatal": Severity.CRITICAL,
        "emergency": Severity.CRITICAL,
    }
    if text in named:
        return named[text]

    try:
        number = int(text)
    except ValueError:
        return Severity.INFORMATIONAL

    if source == EventSource.SURICATA:
        return {1: Severity.HIGH, 2: Severity.MEDIUM, 3: Severity.LOW}.get(
            number, Severity.INFORMATIONAL
        )

    return {
        0: Severity.CRITICAL,
        1: Severity.CRITICAL,
        2: Severity.HIGH,
        3: Severity.MEDIUM,
        4: Severity.LOW,
    }.get(number, Severity.INFORMATIONAL)


class EventNormalizer:
    """Maps common vendor fields into the internal OCSF-aligned event envelope."""

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        sensor_id: str,
        tenant_id: str = "default",
        source_type: str | None = None,
    ) -> SecurityEvent:
        source = _source(
            source_type or _pick(payload, "source_type", "event.module", "module", "observer.type")
        )
        timestamp = _pick(payload, "@timestamp", "event_time", "timestamp", "time", "event.created")
        category = _category(
            _pick(payload, "category", "event.category", "event_type", "type")
        )
        action = _as_text(
            _pick(
                payload,
                "action",
                "event.action",
                "event_type",
                "signature",
                "name",
                "message",
                default="unknown",
            )
        ) or "unknown"
        outcome = _outcome(
            _pick(payload, "outcome", "event.outcome", "result", "status")
        )
        severity = _severity(
            _pick(payload, "severity", "event.severity", "level", "priority"),
            source,
        )

        source_ip = _pick(payload, "src_ip", "source.ip", "src.ip", "source_address")
        dest_ip = _pick(payload, "dst_ip", "destination.ip", "dest.ip", "destination_address")
        source_port = _pick(payload, "src_port", "source.port", "src.port")
        dest_port = _pick(payload, "dst_port", "destination.port", "dest.port")
        tags = _pick(payload, "tags", "event.tags", default=[])
        if not isinstance(tags, list):
            tags = [str(tags)]

        raw_id = _pick(payload, "event_id", "event.id", "id")
        fields: dict[str, Any] = {
            "event_time": _parse_time(timestamp),
            "tenant_id": tenant_id,
            "sensor_id": sensor_id,
            "source_type": source,
            "source_product": _as_text(
                _pick(payload, "source_product", "observer.product", "agent.name")
            ),
            "category": category,
            "action": action,
            "outcome": outcome,
            "severity": severity,
            "host": _as_text(
                _pick(payload, "host.name", "hostname", "computer_name", "host")
            ),
            "principal": _as_text(
                _pick(payload, "principal", "user.name", "user", "username", "account.name")
            ),
            "src_ip": source_ip,
            "dst_ip": dest_ip,
            "src_port": source_port,
            "dst_port": dest_port,
            "process_name": _as_text(
                _pick(payload, "process.name", "process_name", "image")
            ),
            "message": _as_text(_pick(payload, "message", "event.original", "msg")),
            "tags": [str(tag) for tag in tags],
            "raw_event": payload,
        }
        if raw_id is not None:
            fields["event_id"] = str(raw_id)
        return SecurityEvent(**fields)
