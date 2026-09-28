"""Shared memory — Skynet's single source of truth.

Every app reads and writes here, so Foreman, Subtext, Health, etc. can share
state instead of each keeping its own private data. This mirrors the structure
of Joe's Drive "Brain" (contracting / finance / apps / health / personal), but
it is *structured* (queryable JSON) rather than free-form markdown.

Two shapes of data live under each namespace:

    facts    — key/value settings and single values      (get / set / delete)
    series   — append-only, timestamped records           (append / query)

Example:
    mem = MemoryStore(Path("data"))
    mem.set("health", "weight_goal_lbs", 185)
    mem.append("health", "metrics", {"type": "weight", "value": 190})
    mem.query("health", "metrics", where=lambda r: r["type"] == "weight")

Storage is one JSON file per namespace, written atomically. No third-party deps.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


def _now_iso() -> str:
    """UTC timestamp, ISO-8601 with a trailing Z (sorts lexicographically)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MemoryStore:
    """A tiny namespaced document store backed by JSON files on disk."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- internal file handling ------------------------------------------------

    def _path(self, namespace: str) -> Path:
        if not namespace or "/" in namespace or namespace.startswith("."):
            raise ValueError(f"Invalid namespace: {namespace!r}")
        return self.root / f"{namespace}.json"

    def _load(self, namespace: str) -> dict:
        path = self._path(namespace)
        if not path.exists():
            return {"facts": {}, "series": {}}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("facts", {})
        data.setdefault("series", {})
        return data

    def _save(self, namespace: str, data: dict) -> None:
        path = self._path(namespace)
        # Atomic write: temp file in the same dir, then replace.
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    # -- facts (key/value) -----------------------------------------------------

    def set(self, namespace: str, key: str, value: Any) -> None:
        data = self._load(namespace)
        data["facts"][key] = value
        self._save(namespace, data)

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._load(namespace)["facts"].get(key, default)

    def delete(self, namespace: str, key: str) -> bool:
        data = self._load(namespace)
        existed = key in data["facts"]
        data["facts"].pop(key, None)
        if existed:
            self._save(namespace, data)
        return existed

    def facts(self, namespace: str) -> dict:
        return dict(self._load(namespace)["facts"])

    # -- series (append-only records) -----------------------------------------

    def append(self, namespace: str, collection: str, record: dict) -> dict:
        """Append a record; stamps it with an id and 'at' time if absent."""
        data = self._load(namespace)
        series = data["series"].setdefault(collection, [])
        entry = dict(record)
        entry.setdefault("id", uuid.uuid4().hex[:12])
        entry.setdefault("at", _now_iso())
        series.append(entry)
        self._save(namespace, data)
        return entry

    def query(
        self,
        namespace: str,
        collection: str,
        where: Callable[[dict], bool] | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[dict]:
        series = self._load(namespace)["series"].get(collection, [])
        rows: Iterable[dict] = series
        if since is not None:
            rows = (r for r in rows if r.get("at", "") >= since)
        if until is not None:
            rows = (r for r in rows if r.get("at", "") <= until)
        if where is not None:
            rows = (r for r in rows if where(r))
        # Sort ascending by timestamp with a stable sort so that records sharing
        # the same 'at' keep append order; reverse afterwards for newest-first.
        # This makes the last-appended of a same-second tie the "newest".
        ordered = sorted(rows, key=lambda r: r.get("at", ""))
        if newest_first:
            ordered.reverse()
        if limit is not None:
            ordered = ordered[:limit]
        return list(ordered)

    def latest(
        self,
        namespace: str,
        collection: str,
        where: Callable[[dict], bool] | None = None,
    ) -> dict | None:
        rows = self.query(namespace, collection, where=where, limit=1)
        return rows[0] if rows else None

    def delete_record(self, namespace: str, collection: str, record_id: str) -> bool:
        data = self._load(namespace)
        series = data["series"].get(collection, [])
        remaining = [r for r in series if r.get("id") != record_id]
        changed = len(remaining) != len(series)
        if changed:
            data["series"][collection] = remaining
            self._save(namespace, data)
        return changed

    def collections(self, namespace: str) -> list[str]:
        return sorted(self._load(namespace)["series"].keys())

    # -- introspection ---------------------------------------------------------

    def namespaces(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
