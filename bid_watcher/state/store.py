from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    source        TEXT NOT NULL,
    message_id    TEXT NOT NULL,
    account_email TEXT NOT NULL,
    processed_at  TEXT NOT NULL,
    is_bid        INTEGER NOT NULL,
    folder_path   TEXT,
    PRIMARY KEY (source, message_id)
);

CREATE TABLE IF NOT EXISTS source_cursor (
    source        TEXT PRIMARY KEY,
    last_seen_at  TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def is_processed(self, source: str, message_id: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM processed_messages WHERE source = ? AND message_id = ?",
                (source, message_id),
            ).fetchone()
            return row is not None

    def mark_processed(
        self,
        source: str,
        message_id: str,
        account_email: str,
        is_bid: bool,
        folder_path: Optional[str],
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO processed_messages
                    (source, message_id, account_email, processed_at, is_bid, folder_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    message_id,
                    account_email,
                    datetime.now(timezone.utc).isoformat(),
                    1 if is_bid else 0,
                    folder_path,
                ),
            )

    def get_cursor(self, source: str) -> Optional[datetime]:
        with self._conn() as c:
            row = c.execute("SELECT last_seen_at FROM source_cursor WHERE source = ?", (source,)).fetchone()
            if row is None:
                return None
            return datetime.fromisoformat(row[0])

    def set_cursor(self, source: str, when: datetime) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO source_cursor (source, last_seen_at) VALUES (?, ?)",
                (source, when.astimezone(timezone.utc).isoformat()),
            )
