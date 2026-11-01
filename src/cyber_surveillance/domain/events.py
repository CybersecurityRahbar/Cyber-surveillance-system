from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator


class EventSource(StrEnum):
    WAZUH = "wazuh"
    ZEEK = "zeek"
    SURICATA = "suricata"
    OSQUERY = "osquery"
    SYSLOG = "syslog"
    WINDOWS_EVENT = "windows_event"
    LINUX_AUDIT = "linux_audit"
    CLOUD = "cloud"
    API = "api"
    TEST = "test"
    OTHER = "other"


class EventCategory(StrEnum):
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    PROCESS = "process"
    FILE = "file"
    DNS = "dns"
    TLS = "tls"
    CLOUD = "cloud"
    SYSTEM = "system"
    OTHER = "other"


class EventOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEvent(BaseModel):
    """Normalized security event; the original source payload is retained."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    event_time: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "0.1"
    normalizer_version: str = "0.1"
    tenant_id: str = Field(default="default", min_length=1, max_length=128)
    sensor_id: str = Field(min_length=1, max_length=160)
    source_type: EventSource = EventSource.OTHER
    source_product: str | None = Field(default=None, max_length=160)
    category: EventCategory = EventCategory.OTHER
    action: str = Field(default="unknown", min_length=1, max_length=512)
    outcome: EventOutcome = EventOutcome.UNKNOWN
    severity: Severity = Severity.INFORMATIONAL
    host: str | None = Field(default=None, max_length=255)
    principal: str | None = Field(default=None, max_length=255)
    src_ip: IPvAnyAddress | None = None
    dst_ip: IPvAnyAddress | None = None
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dst_port: int | None = Field(default=None, ge=0, le=65535)
    process_name: str | None = Field(default=None, max_length=512)
    message: str | None = Field(default=None, max_length=8192)
    tags: list[str] = Field(default_factory=list, max_length=64)
    raw_event: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_time", "ingested_at")
    @classmethod
    def require_timezone_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone.")
        return value.astimezone(UTC)
