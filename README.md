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
python3 -m skynet run foreman photo

# Run automation checks (e.g. "nudge me if I haven't logged weight")
python3 -m skynet check
```

Tip: add `alias skynet="python3 -m skynet"` to your shell so you can just type
`skynet health summary`.

## The apps Skynet knows about

| App | Status | What it is |
| --- | --- | --- |
| **Health** | live | Tracks weight, sleep, workouts, BP, steps |
| Foreman | external | Job/field management (site photos, notes) |
| Subtext | external | Automated iMessage follow-ups |
| Selections | external | Client finish/product selections |
| Punch List | external | End-of-job punch items |
| Brain Notes | external | The Drive "Brain" markdown memory |

*live* = runs inside Skynet. *external* = runs on the Mac/Cowork; Skynet
coordinates it via shared memory and returns an "intent" rather than pretending
to run it. See the architecture doc for how to promote an external app to live.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Layout

```
skynet/            the brain (engine + apps)
  brain.py         orchestrator: dispatch / emit / check
  memory.py        shared source of truth
  registry.py      loads the app catalogue
  automations.py   the rules engine
  cli.py           the `skynet ...` command line
  apps/
    base.py        BaseApp / AppResult
    health.py      the Health tracker (first live app)
registry/apps.json     the app catalogue (edit to add apps)
automations/rules.json the automation rules
data/memory/           live shared data (gitignored — personal)
docs/ARCHITECTURE.md   how it all fits together
connectors/dropbox/    (legacy) Dropbox connector — superseded by Google Drive
```
