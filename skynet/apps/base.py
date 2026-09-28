"""Base class for Skynet apps.

An "app" here is an adapter: a small Python class that knows how to carry out
the functions the registry advertises for it. The brain loads live apps by their
registry `location` ("module:Class") and dispatches commands to them.

Apps come in two honest flavours:

  * In-process apps (like Health) actually do the work here and return data.
  * Bridge apps (like Foreman / Subtext, which run on Joe's Mac) can't be run
    from inside Skynet. Instead of pretending, their command returns an
    AppResult with an `intent` — a description of what should happen — plus any
    data written to shared memory. That keeps the brain honest about what it can
    and can't directly execute, while still coordinating state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a circular import at runtime
    from ..brain import Brain


@dataclass
class AppResult:
    """The outcome of dispatching a command to an app."""

    ok: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    intent: str | None = None          # for bridge apps: what a human/agent should do
    events: list[dict] = field(default_factory=list)  # events to emit after success

    @classmethod
    def done(cls, summary: str, **data: Any) -> "AppResult":
        return cls(ok=True, summary=summary, data=data)

    @classmethod
    def fail(cls, summary: str, **data: Any) -> "AppResult":
        return cls(ok=False, summary=summary, data=data)

    @classmethod
    def bridge(cls, intent: str, summary: str = "", **data: Any) -> "AppResult":
        return cls(ok=True, summary=summary or intent, intent=intent, data=data)


class BaseApp:
    """Subclass this and implement command handlers named `cmd_<name>`."""

    #: Registry id this adapter serves. Subclasses must set it.
    id: str = ""

    def __init__(self, brain: "Brain"):
        self.brain = brain
        self.memory = brain.memory

    def invoke(self, command: str, params: dict[str, Any] | None = None) -> AppResult:
        handler = getattr(self, f"cmd_{command}", None)
        if handler is None or not callable(handler):
            return AppResult.fail(
                f"{self.id!r} has no command {command!r}. "
                f"Known: {', '.join(self.commands()) or '(none)'}"
            )
        return handler(**(params or {}))

    def commands(self) -> list[str]:
        return sorted(
            name[4:] for name in dir(self) if name.startswith("cmd_")
        )
