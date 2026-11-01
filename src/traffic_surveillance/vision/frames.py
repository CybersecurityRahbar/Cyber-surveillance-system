from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from traffic_surveillance.domain.models import TimestampQuality


@dataclass(frozen=True)
class FramePacket:
    camera_id: str
    frame_index: int
    frame: Any
    timestamp_seconds: float
    timestamp_quality: TimestampQuality


class OpenCVFrameSource:
    """Read a local video, webcam or RTSP stream through OpenCV.

    OpenCV's media-position value is marked estimated, not as exact source PTS.
    Live streams use arrival monotonic time. Neither timestamp type is by itself
    accepted for enforcement-grade speed calculations.
    """

    def __init__(self, camera_id: str, source: str | int) -> None:
        self.camera_id = camera_id
        self.source = source

    def frames(self) -> Iterator[FramePacket]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required. Install the optional 'vision' dependencies."
            ) from exc

        import time

        capture = cv2.VideoCapture(self.source)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Could not open video source for camera {self.camera_id!r}.")

        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                if isinstance(self.source, str) and not self.source.lower().startswith(
                    ("rtsp://", "rtsps://", "http://", "https://")
                ):
                    timestamp = max(0.0, capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
                    quality = TimestampQuality.MEDIA_TIME_ESTIMATED
                else:
                    timestamp = time.monotonic()
                    quality = TimestampQuality.ARRIVAL_MONOTONIC

                yield FramePacket(
                    camera_id=self.camera_id,
                    frame_index=frame_index,
                    frame=frame,
                    timestamp_seconds=timestamp,
                    timestamp_quality=quality,
                )
                frame_index += 1
        finally:
            capture.release()
