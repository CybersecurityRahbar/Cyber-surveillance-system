import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from traffic_surveillance.api.app import create_app
from traffic_surveillance.core.config import Settings
from traffic_surveillance.lab.phone_stream import LatestFrameBuffer


def _jpeg(value: int) -> bytes:
    frame = np.full((48, 64, 3), value, dtype=np.uint8)
    success, encoded = cv2.imencode(".jpg", frame)
    assert success
    return encoded.tobytes()


def test_latest_frame_buffer_drops_stale_frames_and_keeps_latest():
    source = LatestFrameBuffer()
    assert source.push_jpeg(_jpeg(20))
    assert source.push_jpeg(_jpeg(220))

    assert source.received_frames == 2
    assert source.dropped_frames == 1
    packet = source.read_frame(timeout=0.1)
    assert packet is not None
    frame, received_at, received_at_utc = packet
    assert frame.shape == (48, 64, 3)
    assert frame.mean() > 150
    assert received_at > 0
    assert received_at_utc.endswith("+00:00")

    source.close()
    assert source.closed
    assert source.read_frame(timeout=0.1) is None


def test_latest_frame_buffer_rejects_bad_or_oversized_payloads():
    source = LatestFrameBuffer(max_jpeg_bytes=128)
    assert not source.push_jpeg(b"not a jpeg")
    assert not source.push_jpeg(b"\\xff\\xd8" + b"x" * 200 + b"\\xff\\xd9")
    assert source.received_frames == 0
    assert source.dropped_frames == 0
    source.close()


def _phone_client(tmp_path):
    app = create_app(
        Settings(
            environment="test",
            api_key="colab-test-key-with-sufficient-length",
            database=str(tmp_path / "events.sqlite3"),
            lab_storage_dir=str(tmp_path / "lab"),
        )
    )
    return TestClient(app)


def test_phone_websocket_accepts_matching_api_key(tmp_path):
    client = _phone_client(tmp_path)

    with client.websocket_connect(
        "/api/v1/phone/stream/road-01",
        headers={"X-API-Key": "colab-test-key-with-sufficient-length"},
    ) as websocket:
        message = websocket.receive_json()
        assert message["status"] == "connected"
        assert message["camera_id"] == "road-01"
        assert message["transport"] == "websocket-jpeg"


def test_phone_websocket_reports_bad_api_key_as_close_code_not_http_403(tmp_path):
    client = _phone_client(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/v1/phone/stream/road-01",
            headers={"X-API-Key": "incorrect-test-key-with-sufficient-length"},
        ) as websocket:
            websocket.receive_json()

    assert exc_info.value.code == 4401


def test_phone_websocket_reports_invalid_camera_id_after_upgrade(tmp_path):
    client = _phone_client(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/v1/phone/stream/invalid.id",
            headers={"X-API-Key": "colab-test-key-with-sufficient-length"},
        ) as websocket:
            websocket.receive_json()

    assert exc_info.value.code == 4400


def test_latest_frame_buffer_measures_recent_incoming_fps():
    source = LatestFrameBuffer()
    assert source.push_jpeg(_jpeg(30))
    time.sleep(0.02)
    assert source.push_jpeg(_jpeg(60))

    assert source.received_frames == 2
    assert source.received_fps > 0
    source.close()



def test_reconnecting_phone_source_survives_socket_replacement():
    from traffic_surveillance.lab.phone_stream import ReconnectingPhoneSource

    streams = {}
    source = ReconnectingPhoneSource(streams, "road-01", poll_interval=0.01)

    first = LatestFrameBuffer()
    streams["road-01"] = first
    first.push_jpeg(_jpeg(50))
    packet = source.read_frame(timeout=0.2)
    assert packet is not None and packet[0].mean() > 35

    first.close()
    streams.pop("road-01", None)
    assert source.closed is False
    assert source.read_frame(timeout=0.05) is None
    assert source.closed is False

    second = LatestFrameBuffer()
    streams["road-01"] = second
    second.push_jpeg(_jpeg(210))
    packet = source.read_frame(timeout=0.2)
    assert packet is not None and packet[0].mean() > 180
    assert source.received_frames == 2

    source.close()
    assert source.closed is True
    assert source.read_frame(timeout=0.05) is None
