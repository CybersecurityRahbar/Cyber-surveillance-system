from fastapi.testclient import TestClient

from traffic_surveillance.api.app import create_app
from traffic_surveillance.core.config import Settings


def test_lab_ui_and_capabilities_are_available(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)

    page = client.get("/lab")
    assert page.status_code == 200
    assert "مختبر" in page.text
    assert "الرصد المروري المباشر" in page.text
    assert "liveTrackList" in page.text
    assert "trackReportBody" in page.text
    assert "/lab-assets/lab.js" in page.text
    assert client.get("/lab-assets/lab.js").status_code == 200

    capabilities = client.get("/api/v1/lab/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["model"] == "yolo26n.pt"
    assert capabilities.json()["file_profile"]["inference_size"] == 384
    assert capabilities.json()["file_profile"]["max_det"] == 40
    assert capabilities.json()["phone_streaming"]["implemented_in_phone_app"] is True
    assert capabilities.json()["vehicle_make_model_configured"] is False


def test_live_source_validation_rejects_non_stream_urls(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/lab/live-jobs",
        json={"source": "https://example.com/video.mp4"},
    )
    assert response.status_code == 422



def test_api_key_protects_lab_api_but_keeps_ui_reachable(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            api_key="colab-test-key-with-sufficient-length",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)

    assert client.get("/lab").status_code == 200
    assert client.get("/lab-assets/lab.js").status_code == 200
    assert client.get("/api/v1/lab/capabilities").status_code == 401

    authorized = client.get(
        "/api/v1/lab/capabilities",
        headers={"X-API-Key": "colab-test-key-with-sufficient-length"},
    )
    assert authorized.status_code == 200



def test_mjpeg_preview_stream_and_lab_report_routes(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)
    manager = app.state.lab_jobs
    job_id = manager.create(
        source_type="uploaded_video",
        source_label="Local video upload",
        filename="sample.mp4",
        options={},
    )
    jpeg = bytes([255, 216]) + b"test-jpeg" + bytes([255, 217])
    manager.set_preview(job_id, jpeg)
    manager.update(job_id, status="completed")

    streamed = client.get(f"/api/v1/lab/jobs/{job_id}/preview.mjpg")
    assert streamed.status_code == 200
    assert "multipart/x-mixed-replace" in streamed.headers["content-type"]
    assert b"Content-Type: image/jpeg" in streamed.content
    assert jpeg in streamed.content

    app.state.event_store.save_lab_report(
        session_id=job_id,
        source_type="uploaded_video",
        source_label="Local video upload",
        filename="sample.mp4",
        status="completed",
        started_at="2026-11-03T10:00:00+00:00",
        finished_at="2026-11-03T10:00:02+00:00",
        summary={"frames_processed": 5},
        tracks=[{
            "track_id": 42,
            "object_type": "vehicle",
            "class_label": "CAR",
            "frames_seen": 5,
            "first_seen_seconds": 0.0,
            "last_seen_seconds": 1.0,
        }],
    )
    report = client.get(f"/api/v1/lab/reports/{job_id}")
    tracks = client.get(f"/api/v1/lab/reports/{job_id}/tracks")
    assert report.status_code == 200
    assert report.json()["summary"]["frames_processed"] == 5
    assert tracks.status_code == 200
    assert tracks.json()[0]["track_id"] == 42


def test_live_runtime_profile_reads_colab_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_PROFILE", "colab-test")
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_IMAGE_SIZE", "416")
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_MAX_DET", "24")
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_MAX_WIDTH", "800")
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_TRACKER", "bytetrack.yaml")
    monkeypatch.setenv("TRAFFIC_SURVEILLANCE_LIVE_DURATION_SECONDS", "0")

    from traffic_surveillance.api.lab_routes import LiveLabRequest

    request = LiveLabRequest(source="phone-camera:road-01")
    assert request.duration_seconds == 0
    assert request.max_width == 800
    assert request.tracker == "bytetrack.yaml"

    app = create_app(
        Settings(
            environment="test",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)
    profile = client.get("/api/v1/lab/capabilities").json()["realtime_profile"]
    assert profile["profile"] == "colab-test"
    assert profile["input_width"] == 800
    assert profile["inference_size"] == 416
    assert profile["max_det"] == 24
    assert profile["tracker"] == "bytetrack.yaml"
    assert profile["live_video_recording"] is False
    assert profile["continuous_until_stopped"] is True



def test_saved_report_video_endpoint_serves_completed_session(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    client = TestClient(app)
    session_id = "session-video-123"
    report_dir = tmp_path / "lab" / "results"
    report_dir.mkdir(parents=True, exist_ok=True)
    video_path = report_dir / f"{session_id}.mp4"
    video_path.write_bytes(b"test-mp4-content")
    app.state.event_store.save_lab_report(
        session_id=session_id,
        source_type="phone_camera",
        source_label="Phone camera road-01",
        filename="Live session",
        status="completed",
        started_at="2026-11-04T10:00:00+00:00",
        finished_at="2026-11-04T10:00:10+00:00",
        summary={"output_video_available": True},
        tracks=[],
    )

    response = client.get(f"/api/v1/lab/reports/{session_id}/video")
    assert response.status_code == 200
    assert response.content == b"test-mp4-content"
