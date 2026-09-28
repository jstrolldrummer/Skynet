"""The Brain — Skynet's orchestrator.

It ties the four parts together:

    registry     what apps exist and what they do
    memory       the shared source of truth
    automations  the when-X-do-Y rules
    (adapters)   live app instances, loaded on demand from registry `location`

and gives the rest of the system three verbs:

    dispatch(app, command, params)  route a command to an app
    emit(event_name, payload)       announce something happened -> run event rules
    check()                         evaluate check-rules against memory -> fire due ones
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .apps.base import AppResult, BaseApp
from .automations import Automations, Rule
from .memory import MemoryStore
from .registry import Registry

# Repo root = parent of the skynet/ package directory.
_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parent


class Brain:
    def __init__(
        self,
        memory: MemoryStore,
        registry: Registry,
        automations: Automations,
    ):
        self.memory = memory
        self.registry = registry
        self.automations = automations
        self._adapters: dict[str, BaseApp] = {}
        #: Collected notifications from the last emit()/check() run.
        self.outbox: list[str] = []

    # -- construction ---------------------------------------------------------

    @classmethod
    def default(cls, root: str | Path | None = None) -> "Brain":
        """Load the brain from the repo's standard locations."""
        base = Path(root) if root else _REPO_ROOT
        memory = MemoryStore(base / "data" / "memory")
        registry = Registry.load(base / "registry" / "apps.json")
        automations = Automations.load(base / "automations" / "rules.json")
        return cls(memory, registry, automations)

    # -- app loading & dispatch ----------------------------------------------

    def adapter(self, app_id: str) -> BaseApp:
        """Instantiate (and cache) the live adapter for an app id."""
        if app_id in self._adapters:
            return self._adapters[app_id]
        app = self.registry.get(app_id)
        if app is None:
            raise KeyError(f"Unknown app: {app_id!r}")
        if not app.is_live:
            raise ValueError(
                f"App {app_id!r} is not live (status={app.status!r}); "
                "it has no runnable adapter yet."
            )
        module_path, _, class_name = app.location.partition(":")
        module = importlib.import_module(module_path)
        adapter_cls = getattr(module, class_name)
        adapter = adapter_cls(self)
        self._adapters[app_id] = adapter
        return adapter

    def dispatch(
        self, app_id: str, command: str, params: dict[str, Any] | None = None
    ) -> AppResult:
        """Route a command to an app and process any events it returns."""
        app = self.registry.get(app_id)
        if app is None:
            return AppResult.fail(f"Unknown app: {app_id!r}")
        if not app.is_live:
            fn = app.function(command)
            hint = f" ({fn.usage})" if fn and fn.usage else ""
            return AppResult.bridge(
                intent=f"{app.name}: {command}{hint} — runs outside Skynet "
                f"(status: {app.status}).",
                summary=f"{app.name} is a {app.status} app; no in-process adapter.",
            )
        result = self.adapter(app_id).invoke(command, params)
        if result.ok:
            for event in result.events:
                self.emit(event.get("name", ""), event.get("payload", {}))
        return result

    # -- events & automations -------------------------------------------------

    def emit(self, event_name: str, payload: dict[str, Any] | None = None) -> list[Rule]:
        """Announce an event; run matching event-rules. Returns the rules fired."""
        fired = []
        for rule in self.automations.for_event(event_name):
            self._run_actions(rule, {"event": event_name, "payload": payload or {}})
            fired.append(rule)
        return fired

    def check(self) -> list[Rule]:
        """Evaluate all check-rules against memory; fire those whose condition holds."""
        fired = []
        for rule in self.automations.check_rules():
            if self._condition_met(rule.trigger):
                self._run_actions(rule, {"rule": rule.id})
                fired.append(rule)
        return fired

    def _condition_met(self, trigger: dict[str, Any]) -> bool:
        stale = trigger.get("stale")
        if stale:
            return self._is_stale(stale)
        # Unknown/empty condition never fires (fail closed).
        return False

    def _is_stale(self, spec: dict[str, Any]) -> bool:
        """True if the newest matching record is older than `days` (or none exist)."""
        where_spec = spec.get("where", {})
        rows = self.memory.query(
            spec["namespace"],
            spec["collection"],
            where=lambda r: all(r.get(k) == v for k, v in where_spec.items()),
            limit=1,
        )
        if not rows:
            return True
        last_at = rows[0].get("at", "")
        try:
            last = datetime.strptime(last_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=spec.get("days", 1))
        return last < cutoff

    def _run_actions(self, rule: Rule, context: dict[str, Any]) -> None:
        for action in rule.actions:
            self._run_action(rule, action, context)

    def _run_action(
        self, rule: Rule, action: dict[str, Any], context: dict[str, Any]
    ) -> None:
        kind = action.get("type")
        if kind == "notify":
            self.outbox.append(action.get("message", f"[{rule.id}] fired"))
        elif kind == "memory_set":
            self.memory.set(action["namespace"], action["key"], action.get("value"))
        elif kind == "app_invoke":
            self.dispatch(action["app"], action["command"], action.get("params", {}))
        else:
            self.outbox.append(f"[{rule.id}] unknown action type: {kind!r}")

    # -- overview -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        apps = self.registry.all()
        return {
            "apps_total": len(apps),
            "apps_live": [a.id for a in apps if a.is_live],
            "apps_other": [f"{a.id} ({a.status})" for a in apps if not a.is_live],
            "automations": len(self.automations.enabled_rules()),
            "memory_namespaces": self.memory.namespaces(),
        }
