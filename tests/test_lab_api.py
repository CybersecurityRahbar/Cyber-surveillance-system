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
    assert "مختبر الرؤية والتتبع" in page.text
    assert "/lab-assets/lab.js" in page.text
    assert client.get("/lab-assets/lab.js").status_code == 200

    capabilities = client.get("/api/v1/lab/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["model"] == "yolo26n.pt"
    assert capabilities.json()["phone_streaming"]["media_gateway"] == "MediaMTX"


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
