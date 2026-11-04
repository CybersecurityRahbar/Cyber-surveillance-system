from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from queue import Empty, Full, Queue
from threading import Event, Lock
from time import monotonic


class LatestFrameBuffer:
    """Bounded live-video ingress: keep the newest JPEG without building a backlog."""

    def __init__(self, max_jpeg_bytes: int = 4 * 1024 * 1024) -> None:
        self._queue: Queue[tuple[bytes, float, str] | None] = Queue(maxsize=1)
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
            received_at_utc = datetime.now(UTC).isoformat(timespec="milliseconds")
            self._arrival_times.append(received_at)
            item = (bytes(payload), received_at, received_at_utc)
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
        payload, arrived_at, arrived_at_utc = item
        import cv2
        import numpy as np

        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame, arrived_at, arrived_at_utc

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


class ReconnectingPhoneSource:
    """Stable lab source that follows a phone camera across WebSocket reconnects."""

    def __init__(
        self,
        streams: dict[str, LatestFrameBuffer],
        camera_id: str,
        *,
        poll_interval: float = 0.08,
    ) -> None:
        self._streams = streams
        self.camera_id = camera_id
        self._poll_interval = max(0.02, poll_interval)
        self._stopped = Event()
        self._lock = Lock()
        self._accounted: dict[int, tuple[int, int]] = {}
        self._received_total = 0
        self._dropped_total = 0

    def _account(self, stream: LatestFrameBuffer) -> None:
        key = id(stream)
        current_received = int(stream.received_frames)
        current_dropped = int(stream.dropped_frames)
        with self._lock:
            old_received, old_dropped = self._accounted.get(key, (0, 0))
            self._received_total += max(0, current_received - old_received)
            self._dropped_total += max(0, current_dropped - old_dropped)
            self._accounted[key] = (current_received, current_dropped)

    @property
    def received_frames(self) -> int:
        stream = self._streams.get(self.camera_id)
        if stream is not None:
            self._account(stream)
        with self._lock:
            return self._received_total

    @property
    def dropped_frames(self) -> int:
        stream = self._streams.get(self.camera_id)
        if stream is not None:
            self._account(stream)
        with self._lock:
            return self._dropped_total

    @property
    def received_fps(self) -> float:
        stream = self._streams.get(self.camera_id)
        if stream is None or stream.closed:
            return 0.0
        return stream.received_fps

    @property
    def closed(self) -> bool:
        """Disconnects do not close the lab source; only an operator stop does."""
        return self._stopped.is_set()

    def read_frame(self, timeout: float = 1.0):
        deadline = monotonic() + max(0.0, timeout)
        while not self._stopped.is_set():
            stream = self._streams.get(self.camera_id)
            if stream is not None and not stream.closed:
                packet = stream.read_frame(
                    timeout=min(self._poll_interval, max(0.0, deadline - monotonic()))
                )
                self._account(stream)
                if packet is not None:
                    return packet
            if monotonic() >= deadline:
                return None
            self._stopped.wait(
                min(self._poll_interval, max(0.0, deadline - monotonic()))
            )
        return None

    def close(self) -> None:
        self._stopped.set()
