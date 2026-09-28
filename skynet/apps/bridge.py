"""Bridge apps — Skynet's handle on apps that run on Joe's Mac.

Foreman and Subtext can't be executed from inside Skynet, so their commands are
*enqueued* onto the shared bridge queue (see Brain.bridge_enqueue). A small runner
on the Mac polls the queue, performs the action (send the text, capture the
photo), and marks the request done. That gives Skynet real, durable control over
these apps without pretending it can run them itself.

To add a new bridge app: subclass BridgeApp, set `id` and `allowed`, and register
it in registry/apps.json with status "bridge" and a `location`.
"""

from __future__ import annotations

from typing import Any

from .base import AppResult, BaseApp


class BridgeApp(BaseApp):
    """Base for apps whose commands are queued for an external runner."""

    #: Commands this bridge accepts. Empty tuple = accept anything.
    allowed: tuple[str, ...] = ()

    def invoke(self, command: str, params: dict[str, Any] | None = None) -> AppResult:
        if self.allowed and command not in self.allowed:
            return AppResult.fail(
                f"{self.id!r} bridge has no command {command!r}. "
                f"Allowed: {', '.join(self.allowed)}"
            )
        record = self.brain.bridge_enqueue(self.id, command, params or {})
        return AppResult(
            ok=True,
            summary=f"Queued {self.id} · {command} (request {record['id']}). "
            "The Mac-side runner will pick it up.",
            intent=f"{self.id} runner should: {command} {params or ''}".strip(),
            data={"request": record},
            events=[{"name": "bridge.request_created", "payload": record}],
        )

    def commands(self) -> list[str]:
        return list(self.allowed)


class ForemanApp(BridgeApp):
    id = "foreman"
    allowed = ("photo", "note", "job_status")


class SubtextApp(BridgeApp):
    id = "subtext"
    allowed = ("followup", "status")
