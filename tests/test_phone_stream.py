import cv2
import numpy as np

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
    frame, received_at = packet
    assert frame.shape == (48, 64, 3)
    assert frame.mean() > 150
    assert received_at > 0

    source.close()
    assert source.closed
    assert source.read_frame(timeout=0.1) is None


def test_latest_frame_buffer_rejects_bad_or_oversized_payloads():
    source = LatestFrameBuffer(max_jpeg_bytes=128)
    assert not source.push_jpeg(b"not a jpeg")
    assert not source.push_jpeg(b"\xff\xd8" + b"x" * 200 + b"\xff\xd9")
    assert source.received_frames == 0
    assert source.dropped_frames == 0
    source.close()
