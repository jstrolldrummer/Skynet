#!/usr/bin/env python3
"""Skynet command-line interface.

    skynet status                    overview of the whole brain
    skynet apps [--tag personal]     list registered apps
    skynet app health                show one app and its functions
    skynet run <app> <cmd> [k=v...]  route any command to any app
    skynet check                     run automation checks (e.g. nudges)
    skynet emit <event> [k=v...]     announce an event, run matching rules

    skynet health log weight 190 [--unit lbs] [--note "..."]
    skynet health list [--type weight] [--limit 10]
    skynet health summary
    skynet health trend weight [--days 30]
    skynet health goal weight [185]

Run with no arguments for this help.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .apps.base import AppResult
from .brain import Brain


def _print_result(result: AppResult) -> int:
    if result.intent:
        print(f"↪ {result.intent}")
    if result.summary:
        print(result.summary)
    if not result.summary and not result.intent:
        print(json.dumps(result.data, indent=2, default=str))
    return 0 if result.ok else 1


def _kv_pairs(items: list[str]) -> dict[str, Any]:
    """Parse trailing key=value args into a params dict."""
    out: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Expected key=value, got {item!r}")
        key, _, value = item.partition("=")
        out[key] = value
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skynet", description="Skynet master brain")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="overview of the whole brain")

    ap = sub.add_parser("apps", help="list registered apps")
    ap.add_argument("--tag", help="filter by tag")

    one = sub.add_parser("app", help="show one app and its functions")
    one.add_argument("app_id")

    run = sub.add_parser("run", help="route a command to an app")
    run.add_argument("app_id")
    run.add_argument("command")
    run.add_argument("params", nargs="*", help="key=value pairs")

    sub.add_parser("check", help="run automation checks")

    emit = sub.add_parser("emit", help="announce an event")
    emit.add_argument("event")
    emit.add_argument("params", nargs="*", help="key=value pairs")

    serve = sub.add_parser("serve", help="run the web dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    br = sub.add_parser("bridge", help="inspect/complete the bridge queue")
    brsub = br.add_subparsers(dest="bcmd")
    brl = brsub.add_parser("list", help="list queued requests")
    brl.add_argument("--status", choices=["pending", "done", "failed"])
    brc = brsub.add_parser("complete", help="mark a request done")
    brc.add_argument("request_id")
    brc.add_argument("--status", default="done", choices=["done", "failed"])
    brc.add_argument("--result", default="")

    # health app gets first-class subcommands for a nicer experience
    h = sub.add_parser("health", help="health metrics tracker")
    hsub = h.add_subparsers(dest="hcmd")

    hlog = hsub.add_parser("log", help="record a metric")
    hlog.add_argument("type")
    hlog.add_argument("value")
    hlog.add_argument("--unit")
    hlog.add_argument("--note", default="")

    hlist = hsub.add_parser("list", help="recent entries")
    hlist.add_argument("--type")
    hlist.add_argument("--limit", type=int, default=10)

    hsub.add_parser("summary", help="latest reading per metric")

    htrend = hsub.add_parser("trend", help="change over N days")
    htrend.add_argument("type")
    htrend.add_argument("--days", type=int, default=30)

    hgoal = hsub.add_parser("goal", help="set or read a goal")
    hgoal.add_argument("type")
    hgoal.add_argument("value", nargs="?")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    brain = Brain.default()

    if args.cmd == "status":
        s = brain.status()
        print(f"Skynet — {s['apps_total']} apps registered")
        print(f"  live:   {', '.join(s['apps_live']) or '(none)'}")
        print(f"  bridge: {', '.join(s['apps_bridge']) or '(none)'}")
        print(f"  other:  {', '.join(s['apps_other']) or '(none)'}")
        print(f"  automations enabled: {s['automations']}")
        print(f"  bridge queue pending: {s['bridge_pending']}")
        print(f"  memory namespaces: {', '.join(s['memory_namespaces']) or '(none)'}")
        return 0

    if args.cmd == "apps":
        apps = brain.registry.by_tag(args.tag) if args.tag else brain.registry.all()
        for a in apps:
            flag = "●" if a.is_live else "○"
            print(f"{flag} {a.id:<14} {a.status:<9} {a.summary}")
        return 0

    if args.cmd == "app":
        a = brain.registry.get(args.app_id)
        if a is None:
            print(f"Unknown app: {args.app_id!r}")
            return 1
        print(f"{a.name} ({a.id}) — {a.status}")
        print(f"  {a.summary}")
        if a.tags:
            print(f"  tags: {', '.join(a.tags)}")
        print("  functions:")
        for fn in a.functions:
            usage = f"    e.g. {fn.usage}" if fn.usage else ""
            print(f"    - {fn.name}: {fn.summary}{usage}")
        return 0

    if args.cmd == "run":
        return _print_result(
            brain.dispatch(args.app_id, args.command, _kv_pairs(args.params))
        )

    if args.cmd == "check":
        fired = brain.check()
        for msg in brain.outbox:
            print(f"🔔 {msg}")
        print(f"{len(fired)} rule(s) fired.")
        return 0

    if args.cmd == "emit":
        fired = brain.emit(args.event, _kv_pairs(args.params))
        for msg in brain.outbox:
            print(f"🔔 {msg}")
        print(f"{len(fired)} rule(s) fired.")
        return 0

    if args.cmd == "serve":
        from .web import serve as serve_dashboard

        serve_dashboard(brain, host=args.host, port=args.port)
        return 0

    if args.cmd == "bridge":
        bcmd = getattr(args, "bcmd", None)
        if bcmd == "list":
            rows = brain.bridge_queue(status=args.status)
            if not rows:
                print("Bridge queue is empty.")
                return 0
            for r in rows:
                print(
                    f"  [{r['status']:<7}] {r['id']}  {r['app']} · {r['command']}  "
                    f"{r.get('params', {})}"
                )
            print(f"{len(rows)} request(s).")
            return 0
        if bcmd == "complete":
            ok = brain.bridge_complete(
                args.request_id, status=args.status, result=args.result or None
            )
            print("Marked done." if ok else f"No request {args.request_id!r}.")
            return 0 if ok else 1
        print("Usage: skynet bridge {list|complete} ...")
        return 1

    if args.cmd == "health":
        if not getattr(args, "hcmd", None):
            print("Usage: skynet health {log|list|summary|trend|goal} ...")
            return 1
        params = _health_params(args)
        return _print_result(brain.dispatch("health", args.hcmd, params))

    parser.print_help()
    return 0


def _health_params(args: argparse.Namespace) -> dict[str, Any]:
    if args.hcmd == "log":
        p = {"type": args.type, "value": args.value, "note": args.note}
        if args.unit:
            p["unit"] = args.unit
        return p
    if args.hcmd == "list":
        p: dict[str, Any] = {"limit": args.limit}
        if args.type:
            p["type"] = args.type
        return p
    if args.hcmd == "trend":
        return {"type": args.type, "days": args.days}
    if args.hcmd == "goal":
        p = {"type": args.type}
        if args.value is not None:
            p["value"] = args.value
        return p
    return {}


if __name__ == "__main__":
    sys.exit(main())
