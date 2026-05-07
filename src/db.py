"""SQLite layer for tracking seen listings and price history."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


DB_PATH = Path(__file__).parent.parent / "data" / "listings.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    zpid TEXT PRIMARY KEY,
    address TEXT,
    town TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    current_price INTEGER,
    initial_price INTEGER,
    beds REAL,
    baths REAL,
    sqft INTEGER,
    year_built INTEGER,
    days_on_zillow INTEGER,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    zpid TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    price INTEGER NOT NULL,
    PRIMARY KEY (zpid, seen_at)
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    zpid TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    score REAL,
    reason TEXT,
    PRIMARY KEY (zpid, sent_at)
);

CREATE INDEX IF NOT EXISTS idx_listings_town ON listings(town);
CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_listing(listing: dict[str, Any]) -> tuple[bool, int | None]:
    """Insert or update a listing. Returns (is_new, previous_price)."""
    import json

    zpid = str(listing.get("zpid", ""))
    if not zpid:
        return False, None

    now = datetime.utcnow().isoformat(timespec="seconds")
    price = int(listing.get("price") or 0)

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT current_price FROM listings WHERE zpid = ?", (zpid,)
        ).fetchone()

        if existing is None:
            conn.execute(
                """INSERT INTO listings
                   (zpid, address, town, first_seen, last_seen, current_price,
                    initial_price, beds, baths, sqft, year_built, days_on_zillow, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    zpid,
                    listing.get("address"),
                    listing.get("_search_town"),
                    now,
                    now,
                    price,
                    price,
                    listing.get("bedrooms"),
                    listing.get("bathrooms"),
                    listing.get("livingArea"),
                    listing.get("yearBuilt"),
                    listing.get("daysOnZillow"),
                    json.dumps(listing),
                ),
            )
            conn.execute(
                "INSERT INTO price_history (zpid, seen_at, price) VALUES (?, ?, ?)",
                (zpid, now, price),
            )
            return True, None

        prev_price = existing["current_price"]
        conn.execute(
            "UPDATE listings SET last_seen = ?, current_price = ?, raw_json = ? WHERE zpid = ?",
            (now, price, json.dumps(listing), zpid),
        )
        if price != prev_price:
            conn.execute(
                "INSERT OR IGNORE INTO price_history (zpid, seen_at, price) VALUES (?, ?, ?)",
                (zpid, now, price),
            )
        return False, prev_price


def get_price_drop_count(zpid: str) -> int:
    """How many distinct downward price changes have occurred."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT price FROM price_history WHERE zpid = ? ORDER BY seen_at ASC",
            (zpid,),
        ).fetchall()
    if len(rows) < 2:
        return 0
    drops = 0
    for prev, curr in zip(rows, rows[1:]):
        if curr["price"] < prev["price"]:
            drops += 1
    return drops


def get_total_price_drop_pct(zpid: str) -> float:
    """Percent drop from initial listing price to current price."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT initial_price, current_price FROM listings WHERE zpid = ?",
            (zpid,),
        ).fetchone()
    if not row or not row["initial_price"]:
        return 0.0
    return max(0.0, (row["initial_price"] - row["current_price"]) / row["initial_price"])


def record_alert(zpid: str, score: float, reason: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts_sent (zpid, sent_at, score, reason) VALUES (?, ?, ?, ?)",
            (zpid, now, score, reason),
        )


def already_alerted_recently(zpid: str, days: int = 14) -> bool:
    """Avoid re-alerting on the same property unless it dropped further."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT sent_at FROM alerts_sent
               WHERE zpid = ?
               ORDER BY sent_at DESC LIMIT 1""",
            (zpid,),
        ).fetchone()
    if not row:
        return False
    last = datetime.fromisoformat(row["sent_at"])
    return (datetime.utcnow() - last).days < days
