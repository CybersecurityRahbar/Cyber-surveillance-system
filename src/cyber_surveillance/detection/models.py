from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from cyber_surveillance.domain.events import Severity


class AlertStatus(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class SecurityAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    fingerprint: str
    rule_id: str
    rule_version: str
    title: str
    description: str
    severity: Severity
    status: AlertStatus = AlertStatus.NEW
    first_seen: datetime
    last_seen: datetime
    tenant_id: str
    sensor_ids: list[str]
    event_ids: list[str]
    entities: dict[str, str]
    evidence: dict[str, str | int | float]
    attack_techniques: list[str] = Field(default_factory=list)
