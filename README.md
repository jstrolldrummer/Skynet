# Skynet

**The master brain for Wyatt & Gray.** Skynet is the active layer that ties
together the apps and functions built in Cowork — a shared brain that knows what
apps exist, holds one source of truth they all share, routes commands, and runs
automations across them.

> New here? Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture.

## What it does (four simple parts)

- **Registry** — the list of every app and what each can do (`registry/apps.json`)
- **Memory** — one shared store every app reads and writes (`data/memory/`)
- **Automations** — "when X happens, do Y" rules (`automations/rules.json`)
- **Brain** — the orchestrator that routes commands and runs the rules

## Quick start

No installation needed — it's pure Python 3 (standard library only).

```bash
# See everything Skynet knows about
python3 -m skynet status
python3 -m skynet apps
python3 -m skynet app health

# The Health tracker (the first live app)
python3 -m skynet health log weight 190
python3 -m skynet health log sleep 7.5 --note "solid night"
python3 -m skynet health summary
python3 -m skynet health trend weight --days 30
python3 -m skynet health goal weight 185

# Route any command to any app
python3 -m skynet run foreman photo job=24Calhoun

# Run automation checks (e.g. "nudge me if I haven't logged weight")
python3 -m skynet check

# Open the live web dashboard (apps, health, bridge queue)
python3 -m skynet serve            # then open http://127.0.0.1:8787
```

Tip: add `alias skynet="python3 -m skynet"` to your shell so you can just type
`skynet health summary`.

## Controlling your Mac apps (the bridge)

Foreman and Subtext run on your Mac, so Skynet **queues** commands for them and a
small runner drains the queue and does the real work:

```bash
# queue work from anywhere (Cowork, cron, the CLI)
python3 -m skynet run subtext followup to=Mike msg="need the quote"
python3 -m skynet bridge list                 # see what's queued

# on the Mac: drain the queue (wire the handlers to your real tooling)
python3 runners/bridge_poller.py --watch
```

## Connecting your Drive "Brain"

The `brain_notes` app reads/searches/updates your Drive-synced Brain markdown.
Point it at the folder once:

```bash
export SKYNET_BRAIN_DIR="$HOME/Library/CloudStorage/GoogleDrive-joe@wyattgrayhomes.com/My Drive/Apps/Brain"
python3 -m skynet run brain_notes list
python3 -m skynet run brain_notes read path=MASTER.md
python3 -m skynet run brain_notes append path=health/goals.md text="target weight 185"
```

## The apps Skynet knows about

| App | Status | What it is |
| --- | --- | --- |
| **Health** | live | Tracks weight, sleep, workouts, BP, steps |
| **Brain Notes** | live | Reads/updates the Drive "Brain" markdown |
| **Foreman** | bridge | Job/field management (site photos, notes) |
| **Subtext** | bridge | Automated iMessage follow-ups |
| Selections | external | Client finish/product selections |
| Punch List | external | End-of-job punch items |

*live* = runs inside Skynet. *bridge* = runs on the Mac; Skynet queues commands
and a runner drains them. *external* = Skynet knows about it and returns an
"intent". See the architecture doc for how to promote an app between these.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Layout

```
skynet/            the brain (engine + apps)
  brain.py         orchestrator: dispatch / emit / check / bridge queue
  memory.py        shared source of truth
  registry.py      loads the app catalogue
  automations.py   the rules engine
  config.py        machine-specific paths (e.g. the Brain folder)
  web.py           the live web dashboard (stdlib http.server)
  cli.py           the `skynet ...` command line
  apps/
    base.py        BaseApp / AppResult
    health.py      the Health tracker (live)
    brain_notes.py the Drive "Brain" bridge (live)
    bridge.py      Foreman / Subtext bridge apps (queue commands)
registry/apps.json     the app catalogue (edit to add apps)
automations/rules.json the automation rules
runners/bridge_poller.py  sample Mac-side queue runner
data/memory/           live shared data (gitignored — personal)
docs/ARCHITECTURE.md   how it all fits together
connectors/dropbox/    (legacy) Dropbox connector — superseded by Google Drive
```
