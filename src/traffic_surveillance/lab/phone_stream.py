from __future__ import annotations

from collections import deque
from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic


class LatestFrameBuffer:
    """Bounded live-video ingress: always keep the newest JPEG frame, never a backlog."""

    def __init__(self, max_jpeg_bytes: int = 4 * 1024 * 1024) -> None:
        self._queue: Queue[tuple[bytes, float] | None] = Queue(maxsize=1)
        self._lock = Lock()
        self._closed = False
        self._max_jpeg_bytes = max_jpeg_bytes
        self.received_frames = 0
        self.dropped_frames = 0
        self._arrival_times: deque[float] = deque(maxlen=30)

    @property
    def received_fps(self) -> float:
        """Estimate the recent camera-to-server arrival rate over the last 30 frames."""
        with self._lock:
            arrivals = tuple(self._arrival_times)
        if len(arrivals) < 2:
            return 0.0
        interval = arrivals[-1] - arrivals[0]
        return (len(arrivals) - 1) / interval if interval > 0 else 0.0

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def push_jpeg(self, payload: bytes) -> bool:
        if not payload or len(payload) > self._max_jpeg_bytes:
            return False
        if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
            return False
        with self._lock:
            if self._closed:
                return False
            self.received_frames += 1
            received_at = monotonic()
            self._arrival_times.append(received_at)
            item = (bytes(payload), received_at)
            try:
                self._queue.put_nowait(item)
            except Full:
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
                self.dropped_frames += 1
                self._queue.put_nowait(item)
            return True

    def read_frame(self, timeout: float = 1.0):
        try:
            item = self._queue.get(timeout=timeout)
        except Empty:
            return None
        if item is None:
            return None
        payload, arrived_at = item
        import cv2
        import numpy as np

        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame, arrived_at

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._queue.put_nowait(None)
            except Full:
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
                self._queue.put_nowait(None)
