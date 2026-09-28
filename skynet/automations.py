"""Automations — Skynet's "when X, do Y" rules across apps.

Rules live in automations/rules.json (data, editable by a non-coder). Each rule
has a trigger and one or more actions. The brain evaluates rules in two ways:

  * event rules   fire when the brain emits a matching event (e.g. an app did
                  something, or you ran `skynet emit ...`).
  * check rules   are evaluated on demand by `skynet check` (or a scheduler you
                  wire up later, e.g. a cron / Routine). They test a condition
                  against shared memory — for example, "no weight logged in 3
                  days" — and fire their actions when the condition is true.

A rule looks like:

    {
      "id": "nudge_weight",
      "name": "Nudge if no weight logged in 3 days",
      "enabled": true,
      "trigger": {"type": "check",
                  "stale": {"namespace": "health", "collection": "metrics",
                            "where": {"type": "weight"}, "days": 3}},
      "actions": [{"type": "notify",
                   "message": "No weight logged in 3+ days."}]
    }

Actions supported by the brain: notify, memory_set, app_invoke (see brain.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    trigger: dict[str, Any]
    actions: tuple[dict[str, Any], ...]
    enabled: bool = True

    @property
    def trigger_type(self) -> str:
        return self.trigger.get("type", "")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            trigger=d.get("trigger", {}),
            actions=tuple(d.get("actions", [])),
            enabled=d.get("enabled", True),
        )


class Automations:
    def __init__(self, rules: list[Rule] | None = None):
        self.rules: list[Rule] = list(rules or [])

    @classmethod
    def load(cls, path: str | Path) -> "Automations":
        path = Path(path)
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls([Rule.from_dict(r) for r in raw.get("rules", [])])

    def enabled_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.enabled]

    def for_event(self, event_name: str) -> list[Rule]:
        """Event rules whose trigger matches the given event name."""
        out = []
        for r in self.enabled_rules():
            if r.trigger_type == "event" and r.trigger.get("on") == event_name:
                out.append(r)
        return out

    def check_rules(self) -> list[Rule]:
        return [r for r in self.enabled_rules() if r.trigger_type == "check"]
