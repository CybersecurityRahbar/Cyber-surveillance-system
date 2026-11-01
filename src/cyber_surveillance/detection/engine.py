from cyber_surveillance.detection.models import SecurityAlert
from cyber_surveillance.detection.rules import AuthenticationFailureBurstRule
from cyber_surveillance.domain.events import SecurityEvent


class DetectionEngine:
    def __init__(self, rules: list[AuthenticationFailureBurstRule]) -> None:
        self._rules = rules

    def process(self, event: SecurityEvent) -> list[SecurityAlert]:
        alerts: list[SecurityAlert] = []
        for rule in self._rules:
            alert = rule.evaluate(event)
            if alert is not None:
                alerts.append(alert)
        return alerts
