"""Health — Skynet's first live app: a personal metrics tracker.

Logs Joe's health metrics into shared memory (namespace "health", collection
"metrics") and reads them back as recent history, trends, and a summary. Because
it writes to the brain's shared memory, any other app or automation can read the
same data (e.g. a morning brief, or a "nudge if no weight logged" rule).

Commands (see registry/apps.json for the advertised list):

    log      record a metric        -> health log weight 190 [--unit lbs] [--note "..."]
    list     recent entries         -> health list [--type weight] [--limit 10]
    summary  latest of each metric  -> health summary
    trend    change over N days     -> health trend weight [--days 30]
    goal     set/read a target      -> health goal weight 185   |   health goal weight

Known metric types carry a default unit so you can just type `health log weight 190`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import AppResult, BaseApp

# Default units for the metrics Joe is likely to track. Unknown types are allowed
# too (unit defaults to blank) so the tracker never blocks a new kind of metric.
DEFAULT_UNITS: dict[str, str] = {
    "weight": "lbs",
    "sleep": "hrs",
    "steps": "count",
    "workout": "min",
    "resting_hr": "bpm",
    "systolic": "mmHg",
    "diastolic": "mmHg",
    "water": "oz",
    "calories": "kcal",
    "mood": "1-10",
    "weight_lbs": "lbs",
}

NAMESPACE = "health"
COLLECTION = "metrics"


class HealthApp(BaseApp):
    id = "health"

    # -- log ------------------------------------------------------------------

    def cmd_log(
        self,
        type: str,
        value: Any,
        unit: str | None = None,
        note: str = "",
        at: str | None = None,
    ) -> AppResult:
        metric = str(type).strip().lower()
        if not metric:
            return AppResult.fail("A metric type is required, e.g. 'weight'.")
        try:
            num = float(value)
        except (TypeError, ValueError):
            return AppResult.fail(f"Value must be a number, got {value!r}.")

        record: dict[str, Any] = {
            "type": metric,
            "value": num,
            "unit": unit or DEFAULT_UNITS.get(metric, ""),
            "note": note,
        }
        if at:
            record["at"] = at
        saved = self.memory.append(NAMESPACE, COLLECTION, record)
        pretty = _fmt(saved)
        return AppResult(
            ok=True,
            summary=f"Logged {pretty}.",
            data={"record": saved},
            events=[{"name": "health.metric_logged", "payload": saved}],
        )

    # -- list -----------------------------------------------------------------

    def cmd_list(self, type: str | None = None, limit: int = 10) -> AppResult:
        where = None
        if type:
            t = str(type).strip().lower()
            where = lambda r: r.get("type") == t  # noqa: E731
        rows = self.memory.query(NAMESPACE, COLLECTION, where=where, limit=int(limit))
        if not rows:
            return AppResult.done("No metrics logged yet.", records=[])
        lines = [f"  {r.get('at', '?')}  {_fmt(r)}" for r in rows]
        return AppResult.done(
            f"Last {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}:\n"
            + "\n".join(lines),
            records=rows,
        )

    # -- summary --------------------------------------------------------------

    def cmd_summary(self) -> AppResult:
        rows = self.memory.query(NAMESPACE, COLLECTION, newest_first=True)
        if not rows:
            return AppResult.done("No metrics logged yet.", metrics={})
        latest: dict[str, dict] = {}
        for r in rows:  # rows are newest-first, so first seen wins
            latest.setdefault(r.get("type", "?"), r)
        goals = self.memory.get(NAMESPACE, "goals", {}) or {}
        lines = []
        for mtype in sorted(latest):
            r = latest[mtype]
            line = f"  {mtype}: {_fmt(r, with_type=False)}  (as of {r.get('at', '?')})"
            if mtype in goals:
                line += f"  · goal {goals[mtype]}"
            lines.append(line)
        return AppResult.done(
            "Latest reading per metric:\n" + "\n".join(lines),
            metrics={k: v for k, v in latest.items()},
            goals=goals,
        )

    # -- trend ----------------------------------------------------------------

    def cmd_trend(self, type: str, days: int = 30) -> AppResult:
        t = str(type).strip().lower()
        since = _days_ago_iso(int(days))
        rows = self.memory.query(
            NAMESPACE,
            COLLECTION,
            where=lambda r: r.get("type") == t,
            since=since,
            newest_first=False,
        )
        if len(rows) < 2:
            return AppResult.done(
                f"Not enough {t} data in the last {days} days to show a trend "
                f"({len(rows)} point{'s' if len(rows) != 1 else ''}).",
                points=rows,
            )
        first, last = rows[0], rows[-1]
        change = last["value"] - first["value"]
        unit = last.get("unit", "")
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "→")
        return AppResult.done(
            f"{t}: {first['value']}{unit} → {last['value']}{unit} "
            f"{arrow} {change:+.1f}{unit} over {days} days ({len(rows)} readings).",
            change=change,
            first=first,
            last=last,
            count=len(rows),
        )

    # -- goal -----------------------------------------------------------------

    def cmd_goal(self, type: str, value: Any | None = None) -> AppResult:
        t = str(type).strip().lower()
        goals = dict(self.memory.get(NAMESPACE, "goals", {}) or {})
        if value is None:
            if t in goals:
                return AppResult.done(f"Goal for {t}: {goals[t]}.", goal=goals[t])
            return AppResult.done(f"No goal set for {t}.", goal=None)
        goals[t] = value
        self.memory.set(NAMESPACE, "goals", goals)
        return AppResult.done(f"Set goal for {t} to {value}.", goals=goals)


# -- formatting helpers -------------------------------------------------------


def _fmt(record: dict, with_type: bool = True) -> str:
    val = record.get("value")
    unit = record.get("unit", "")
    body = f"{val}{unit}".rstrip()
    if with_type:
        body = f"{record.get('type', '?')} {body}"
    note = record.get("note")
    if note:
        body += f' — "{note}"'
    return body


def _days_ago_iso(days: int) -> str:
    from datetime import timedelta

    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
