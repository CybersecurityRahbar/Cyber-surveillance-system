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



def test_lab_session_and_track_reports_survive_store_reopen(tmp_path):
    path = tmp_path / "lab.sqlite3"
    first = SQLiteEventStore(path)
    first.save_lab_report(
        session_id="session-001",
        source_type="uploaded_video",
        source_label="Local video upload",
        filename="road.mp4",
        status="completed",
        started_at="2026-11-03T10:00:00+00:00",
        finished_at="2026-11-03T10:00:04+00:00",
        summary={"frames_processed": 100, "unique_vehicle_tracks": 1},
        tracks=[{
            "track_id": 42,
            "object_type": "vehicle",
            "class_label": "CAR",
            "vehicle_color": "white",
            "frames_seen": 70,
            "trajectory": [{"frame": 3, "time": 0.1, "x": 42.0, "y": 63.0}],
        }],
    )

    reopened = SQLiteEventStore(path)
    report = reopened.get_lab_report("session-001")
    tracks = reopened.get_lab_tracks("session-001")
    assert report is not None
    assert report["summary"]["frames_processed"] == 100
    assert tracks[0]["track_id"] == 42
    assert tracks[0]["vehicle_color"] == "white"
    assert tracks[0]["trajectory"][0]["x"] == 42.0
    assert len(reopened.list_lab_reports()) == 1
