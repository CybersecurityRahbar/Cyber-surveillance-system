from fastapi.testclient import TestClient

from cyber_surveillance.api.app import create_app
from cyber_surveillance.core.config import Settings


def build_client() -> TestClient:
    settings = Settings(environment="test", api_key="test-secret")
    return TestClient(create_app(settings))


def test_ingest_detects_authentication_burst_and_returns_status() -> None:
    client = build_client()
    headers = {"x-api-key": "test-secret", "content-type": "application/json"}
    events = []
    for index in range(5):
        events.append(
            {
                "event_id": f"login-{index}",
                "@timestamp": f"2026-11-01T10:00:0{index}Z",
                "event": {
                    "category": "authentication",
                    "action": "login",
                    "outcome": "failure",
                    "severity": "medium",
                },
                "user": {"name": "analyst"},
                "source": {"ip": "192.0.2.10"},
                "host": {"name": "lab-host"},
            }
        )

    response = client.post(
        "/api/v1/events/ingest",
        headers=headers,
        json={"sensor_id": "test-sensor", "source_type": "syslog", "events": events},
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": 5, "duplicates": 0, "alerts_created": 1}

    alerts = client.get("/api/v1/alerts", headers=headers)
    assert alerts.status_code == 200
    assert len(alerts.json()) == 1
    assert alerts.json()[0]["rule_id"] == "auth.failure_burst"

    status = client.get("/api/v1/status", headers=headers)
    assert status.json()["events_in_memory"] == 5
    assert status.json()["durable_storage"] is False


def test_ingest_requires_api_key_when_configured() -> None:
    response = build_client().post(
        "/api/v1/events/ingest",
        json={
            "sensor_id": "test-sensor",
            "events": [{"event_id": "event-1", "action": "test"}],
        },
    )
    assert response.status_code == 401


def test_duplicate_event_ids_are_idempotent() -> None:
    client = build_client()
    headers = {"x-api-key": "test-secret"}
    event = {
        "event_id": "same-id",
        "@timestamp": "2026-11-01T10:00:00Z",
        "event": {"category": "system", "action": "service-started"},
    }
    body = {"sensor_id": "test-sensor", "events": [event, event]}

    response = client.post("/api/v1/events/ingest", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "duplicates": 1, "alerts_created": 0}
