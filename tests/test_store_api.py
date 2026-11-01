from datetime import UTC, datetime

from fastapi.testclient import TestClient

from traffic_surveillance.api.app import create_app
from traffic_surveillance.core.config import Settings
from traffic_surveillance.domain.models import EventType, Severity, SurveillanceEvent
from traffic_surveillance.storage.sqlite_store import SQLiteEventStore


def make_event(camera_id: str = "cam-1") -> SurveillanceEvent:
    return SurveillanceEvent(
        camera_id=camera_id,
        event_type=EventType.ZONE_INTRUSION,
        severity=Severity.HIGH,
        occurred_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        title="Zone entry",
        track_id=21,
    )


def test_sqlite_event_store_is_persistent_and_idempotent(tmp_path) -> None:
    path = tmp_path / "events.sqlite3"
    first = SQLiteEventStore(path)
    event = make_event()

    assert first.add_event(event)
    assert not first.add_event(event)

    reopened = SQLiteEventStore(path)
    records = reopened.list_events()
    assert len(records) == 1
    assert records[0].event_id == event.event_id


def test_api_records_and_lists_surveillance_events(tmp_path) -> None:
    settings = Settings(environment="test", database=str(tmp_path / "api.sqlite3"))
    client = TestClient(create_app(settings))
    event = make_event("road-cam-2")

    created = client.post("/api/v1/events", json=event.model_dump(mode="json"))
    assert created.status_code == 201
    listed = client.get("/api/v1/events", params={"camera_id": "road-cam-2"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    status = client.get("/api/v1/status").json()
    assert status["storage"] == "sqlite"
    assert status["events_stored"] == 1
    assert isinstance(status["video_processing_ready"], bool)
