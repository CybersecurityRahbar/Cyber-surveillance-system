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
