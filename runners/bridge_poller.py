#!/usr/bin/env python3
"""Sample bridge runner — runs on Joe's Mac to drain Skynet's bridge queue.

Skynet (which may run in Cowork, a cron, or anywhere) enqueues bridge requests
for Foreman and Subtext. Those apps live on the Mac, so this small script polls
the queue, performs each request with the real local tooling, and marks it done.

How to use:
    1. Keep this repo (and its data/memory/ queue) on the Mac, or point it at the
       shared queue location.
    2. Fill in the handlers below to call the real Subtext / Foreman tooling.
    3. Run it on a schedule (launchd/cron) or leave it running with --watch.

        python3 runners/bridge_poller.py            # drain once
        python3 runners/bridge_poller.py --watch     # poll every 10s

This is intentionally a template: the handlers are stubs that print what they
*would* do, so it's safe to run as-is.
"""

from __future__ import annotations

import argparse
import subprocess  # noqa: F401  (used by real handlers you add)
import sys
import time
from pathlib import Path

# Make the repo importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skynet import Brain  # noqa: E402


def handle_subtext(command: str, params: dict) -> str:
    """Wire this to the real Subtext tooling (~/Subtext)."""
    if command == "followup":
        to, msg = params.get("to", "?"), params.get("msg", "")
        # e.g. subprocess.run(["python3", str(Path.home()/"Subtext/send.py"), to, msg])
        return f"(stub) would text {to}: {msg!r}"
    if command == "status":
        return "(stub) would report the Subtext queue status"
    return f"(stub) unknown subtext command {command!r}"


def handle_foreman(command: str, params: dict) -> str:
    """Wire this to the real Foreman tooling / iOS shortcut."""
    return f"(stub) would run Foreman {command} with {params}"


HANDLERS = {"subtext": handle_subtext, "foreman": handle_foreman}


def drain_once(brain: Brain) -> int:
    pending = brain.bridge_queue(status="pending")
    for req in pending:
        handler = HANDLERS.get(req["app"])
        if handler is None:
            brain.bridge_complete(req["id"], status="failed",
                                  result=f"no handler for app {req['app']!r}")
            print(f"✗ {req['id']} {req['app']}: no handler")
            continue
        try:
            result = handler(req["command"], req.get("params", {}))
            brain.bridge_complete(req["id"], status="done", result=result)
            print(f"✓ {req['id']} {req['app']}·{req['command']}: {result}")
        except Exception as exc:  # keep the runner alive on a single failure
            brain.bridge_complete(req["id"], status="failed", result=str(exc))
            print(f"✗ {req['id']} {req['app']}·{req['command']}: {exc}")
    return len(pending)


def main() -> int:
    ap = argparse.ArgumentParser(description="Drain the Skynet bridge queue.")
    ap.add_argument("--watch", action="store_true", help="poll continuously")
    ap.add_argument("--interval", type=float, default=10.0)
    args = ap.parse_args()

    brain = Brain.default()
    if not args.watch:
        n = drain_once(brain)
        print(f"Processed {n} request(s).")
        return 0

    print(f"Watching bridge queue every {args.interval}s (Ctrl-C to stop)…")
    try:
        while True:
            drain_once(brain)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
