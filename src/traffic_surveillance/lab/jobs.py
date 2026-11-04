from copy import deepcopy
from datetime import UTC, datetime
from threading import Condition, Event, RLock
from uuid import uuid4


class LabJobManager:
    """Thread-safe in-memory session registry for short laboratory jobs."""

    def __init__(self, max_jobs: int = 20) -> None:
        self.max_jobs = max_jobs
        self._lock = RLock()
        self._changed = Condition(self._lock)
        self._jobs: dict[str, dict] = {}
        self._stop_events: dict[str, Event] = {}
        self._previews: dict[str, tuple[int, bytes]] = {}

    def create(
        self,
        *,
        source_type: str,
        source_label: str,
        filename: str,
        options: dict,
    ) -> str:
        job_id = str(uuid4())
        record = {
            "job_id": job_id,
            "source_type": source_type,
            "source_label": source_label,
            "filename": filename,
            "status": "queued",
            "progress": 0.0,
            "frames_processed": 0,
            "total_frames": None,
            "processing_fps": 0.0,
            "source_fps": None,
            "inference_latency_ms": 0.0,
            "frame_age_ms": 0.0,
            "input_frames_received": 0,
            "input_fps": 0.0,
            "input_frames_dropped": 0,
            "current_tracks": [],
            "class_counts": {},
            "current_counts": {},
            "line_crossings": {"down": 0, "up": 0},
            "unique_vehicle_tracks": 0,
            "unique_person_tracks": 0,
            "options": deepcopy(options),
            "created_at": datetime.now(UTC).isoformat(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "result": None,
            "video_url": None,
        }
        with self._lock:
            self._jobs[job_id] = record
            self._stop_events[job_id] = Event()
            while len(self._jobs) > self.max_jobs:
                oldest = next(iter(self._jobs))
                self._jobs.pop(oldest, None)
                self._stop_events.pop(oldest, None)
                self._previews.pop(oldest, None)
        return job_id

    def update(self, job_id: str, **changes) -> None:
        with self._changed:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)
                self._changed.notify_all()

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return deepcopy(record) if record is not None else None

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            values = list(self._jobs.values())[-limit:]
            return [deepcopy(item) for item in reversed(values)]

    def stop_event(self, job_id: str) -> Event | None:
        with self._lock:
            return self._stop_events.get(job_id)

    def request_stop(self, job_id: str) -> bool:
        with self._lock:
            event = self._stop_events.get(job_id)
            record = self._jobs.get(job_id)
            if event is None or record is None or record["status"] not in {"queued", "running"}:
                return False
            event.set()
            return True

    def set_preview(self, job_id: str, jpeg: bytes) -> None:
        with self._changed:
            if job_id not in self._jobs:
                return
            version = self._previews.get(job_id, (0, b""))[0] + 1
            self._previews[job_id] = (version, jpeg)
            self._changed.notify_all()

    def get_preview(self, job_id: str) -> tuple[int, bytes] | None:
        with self._lock:
            return self._previews.get(job_id)


    def wait_for_preview(
        self,
        job_id: str,
        after_version: int,
        timeout: float = 15.0,
    ) -> tuple[int, bytes] | None:
        terminal = {"completed", "stopped", "failed"}
        with self._changed:
            self._changed.wait_for(
                lambda: (
                    self._previews.get(job_id, (0, b""))[0] > after_version
                    or self._jobs.get(job_id, {}).get("status") in terminal
                    or job_id not in self._jobs
                ),
                timeout=timeout,
            )
            preview = self._previews.get(job_id)
            if preview is not None and preview[0] > after_version:
                return preview
            return None
