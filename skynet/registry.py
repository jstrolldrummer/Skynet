"""The app registry — Skynet's catalogue of every app and what it can do.

The registry is data, not code: it lives in registry/apps.json so a non-coder
can see (and edit) the full list of apps in one place. Each entry describes an
app and the functions it exposes; the brain uses it to route commands and to
answer "what can Skynet do?".

An entry looks like:

    {
      "id": "health",
      "name": "Health",
      "summary": "Tracks Joe's health metrics.",
      "status": "live",              # live | planned | external
      "location": "skynet.apps.health:HealthApp",
      "tags": ["personal"],
      "functions": [
        {"name": "log", "summary": "Record a metric", "usage": "health log weight 190"}
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Function:
    name: str
    summary: str = ""
    usage: str = ""


@dataclass(frozen=True)
class App:
    id: str
    name: str
    summary: str = ""
    status: str = "planned"          # live | planned | external
    location: str = ""               # "module.path:ClassName" for live apps
    tags: tuple[str, ...] = ()
    functions: tuple[Function, ...] = ()

    @property
    def is_live(self) -> bool:
        return self.status == "live" and bool(self.location)

    def function(self, name: str) -> Function | None:
        for fn in self.functions:
            if fn.name == name:
                return fn
        return None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "App":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"].title()),
            summary=d.get("summary", ""),
            status=d.get("status", "planned"),
            location=d.get("location", ""),
            tags=tuple(d.get("tags", [])),
            functions=tuple(
                Function(f["name"], f.get("summary", ""), f.get("usage", ""))
                for f in d.get("functions", [])
            ),
        )


class Registry:
    def __init__(self, apps: list[App] | None = None):
        self._apps: dict[str, App] = {}
        for app in apps or []:
            self._apps[app.id] = app

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        path = Path(path)
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        apps = [App.from_dict(entry) for entry in raw.get("apps", [])]
        return cls(apps)

    def get(self, app_id: str) -> App | None:
        return self._apps.get(app_id)

    def all(self) -> list[App]:
        return sorted(self._apps.values(), key=lambda a: (a.status != "live", a.id))

    def by_tag(self, tag: str) -> list[App]:
        return [a for a in self.all() if tag in a.tags]

    def live(self) -> list[App]:
        return [a for a in self.all() if a.is_live]

    def __len__(self) -> int:
        return len(self._apps)

    def __contains__(self, app_id: object) -> bool:
        return app_id in self._apps
