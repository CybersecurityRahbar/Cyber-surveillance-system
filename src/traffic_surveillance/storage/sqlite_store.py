import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from traffic_surveillance.domain.models import SurveillanceEvent


class SQLiteEventStore:
    """Small durable event store for the first single-node development slice."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS surveillance_events (
                    event_id TEXT PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_surveillance_events_time
                ON surveillance_events (occurred_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_surveillance_events_camera_time
                ON surveillance_events (camera_id, occurred_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lab_sessions (
                    session_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    summary_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lab_sessions_finished
                ON lab_sessions (finished_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lab_tracks (
                    session_id TEXT NOT NULL,
                    track_id INTEGER NOT NULL,
                    object_type TEXT NOT NULL,
                    class_label TEXT NOT NULL,
                    first_seen_seconds REAL,
                    last_seen_seconds REAL,
                    frames_seen INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, track_id),
                    FOREIGN KEY (session_id) REFERENCES lab_sessions(session_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lab_tracks_type
                ON lab_tracks (session_id, object_type, class_label)
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add_event(self, event: SurveillanceEvent) -> bool:
        payload = event.model_dump_json()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO surveillance_events
                (event_id, camera_id, event_type, severity, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.camera_id,
                    event.event_type.value,
                    event.severity.value,
                    event.occurred_at.isoformat(),
                    payload,
                ),
            )
            return cursor.rowcount == 1

    def list_events(
        self,
        *,
        camera_id: str | None = None,
        limit: int = 100,
    ) -> list[SurveillanceEvent]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        query = "SELECT payload_json FROM surveillance_events"
        parameters: tuple[object, ...] = ()
        if camera_id:
            query += " WHERE camera_id = ?"
            parameters = (camera_id,)
        query += " ORDER BY occurred_at DESC LIMIT ?"
        parameters += (limit,)

        with self._lock, self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [SurveillanceEvent.model_validate_json(row["payload_json"]) for row in rows]

    def count_events(self) -> int:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS event_count FROM surveillance_events"
            ).fetchone()
        return int(row["event_count"])


    def save_lab_report(
        self,
        *,
        session_id: str,
        source_type: str,
        source_label: str,
        filename: str,
        status: str,
        started_at: str | None,
        finished_at: str | None,
        summary: dict,
        tracks: list[dict],
    ) -> None:
        summary_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO lab_sessions
                (session_id, source_type, source_label, filename, status,
                 started_at, finished_at, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source_type=excluded.source_type,
                    source_label=excluded.source_label,
                    filename=excluded.filename,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    summary_json=excluded.summary_json
                """,
                (
                    session_id,
                    source_type,
                    source_label,
                    filename,
                    status,
                    started_at,
                    finished_at,
                    summary_json,
                ),
            )
            connection.execute(
                "DELETE FROM lab_tracks WHERE session_id = ?",
                (session_id,),
            )
            connection.executemany(
                """
                INSERT INTO lab_tracks
                (session_id, track_id, object_type, class_label,
                 first_seen_seconds, last_seen_seconds, frames_seen, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        int(track["track_id"]),
                        str(track["object_type"]),
                        str(track["class_label"]),
                        track.get("first_seen_seconds"),
                        track.get("last_seen_seconds"),
                        int(track.get("frames_seen", 0)),
                        json.dumps(track, ensure_ascii=False, separators=(",", ":")),
                    )
                    for track in tracks
                ],
            )

    def get_lab_report(self, session_id: str) -> dict | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """
                SELECT session_id, source_type, source_label, filename, status,
                       started_at, finished_at, summary_json
                FROM lab_sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "source_type": row["source_type"],
            "source_label": row["source_label"],
            "filename": row["filename"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "summary": json.loads(row["summary_json"]),
        }

    def get_lab_tracks(self, session_id: str) -> list[dict]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT report_json FROM lab_tracks
                WHERE session_id = ? ORDER BY first_seen_seconds, track_id
                """,
                (session_id,),
            ).fetchall()
        return [json.loads(row["report_json"]) for row in rows]

    def list_lab_reports(self, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id, source_type, source_label, filename, status,
                       started_at, finished_at, summary_json
                FROM lab_sessions ORDER BY COALESCE(finished_at, started_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "source_type": row["source_type"],
                "source_label": row["source_label"],
                "filename": row["filename"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "summary": json.loads(row["summary_json"]),
            }
            for row in rows
        ]
