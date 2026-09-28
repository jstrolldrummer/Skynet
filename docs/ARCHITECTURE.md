# Skynet Architecture

Skynet is the **master brain** — the active coordination layer over the apps and
functions Joe builds in Cowork. It is deliberately small and made of four parts.

```
                         ┌───────────────────────────┐
        skynet CLI  ───▶ │           BRAIN           │
        (or Python)      │      (orchestrator)       │
                         └───────────────────────────┘
                           │        │            │
              ┌────────────┘        │            └─────────────┐
              ▼                     ▼                          ▼
     ┌────────────────┐   ┌──────────────────┐      ┌────────────────────┐
     │    REGISTRY    │   │      MEMORY      │      │    AUTOMATIONS     │
     │ apps + their   │   │ one shared store │      │ when-X-do-Y rules  │
     │ functions      │   │ every app uses   │      │ (event & check)    │
     └────────────────┘   └──────────────────┘      └────────────────────┘
              │
      ┌───────┴─────────────────────────────┐
      ▼                                      ▼
 ┌──────────┐  (live, in-process)     ┌──────────────┐  (external: run on the
 │  Health  │                         │ Foreman ...  │   Mac/Cowork — Skynet
 └──────────┘                         └──────────────┘   coordinates via memory)
```

## The four parts

| Part | File | What it is |
| --- | --- | --- |
| **Registry** | `registry/apps.json` + `skynet/registry.py` | The catalogue of every app and the functions each exposes. Plain data you can edit. |
| **Memory** | `data/memory/*.json` + `skynet/memory.py` | One shared source of truth. `facts` (key/value) and `series` (append-only, timestamped). Namespaced like the Drive Brain: `health`, `finance`, `contracting`, `personal`. |
| **Automations** | `automations/rules.json` + `skynet/automations.py` | `event` rules (fire on `emit`) and `check` rules (evaluated by `skynet check`). |
| **Brain** | `skynet/brain.py` | Ties them together. Three verbs: `dispatch`, `emit`, `check`. |

## App types (honest about boundaries)

- **live** — an in-process adapter that actually runs here (e.g. **Health**,
  **Brain Notes**). Registry `location` points to `module:Class`; the brain loads
  and calls it.
- **bridge** — apps that run on Joe's Mac (Foreman, Subtext) but that Skynet can
  still drive: a bridge command is **enqueued** onto a shared to-do queue, and a
  small runner on the Mac (`runners/bridge_poller.py`) drains it, does the work,
  and marks it done. Durable, honest control without pretending to execute them.
- **external** — apps Skynet only knows about; a command returns an **intent**
  (a description of what should happen). Promote these to `bridge` or `live`
  when ready.
- **planned** — not built yet.

This is the key design choice: rather than fake control over apps it can't reach,
Skynet is a **shared brain + coordinator**. Any app that writes to Skynet's memory,
gets a live adapter, or is wired to the bridge queue becomes controllable and can
share state with every other app.

## The bridge queue (controlling Mac apps)

```
skynet run subtext followup to=Mike msg="need the quote"
  └▶ brain.dispatch ──▶ SubtextApp (bridge) enqueues a request in memory
        namespace "bridge", collection "queue", status "pending"

… meanwhile, on Joe's Mac …

python3 runners/bridge_poller.py --watch
  └▶ reads pending requests ──▶ runs the real Subtext/Foreman tooling
        └▶ brain.bridge_complete(id, "done", result)  (status flips to done)
```

Fill in the handlers in `runners/bridge_poller.py` to call the real local tools;
schedule it with launchd/cron, or run it with `--watch`.

## The Brain Notes bridge (Drive memory)

`brain_notes` is a **live** app that reads/searches/appends the Drive-synced
"Brain" markdown folder. Point it at the folder with `SKYNET_BRAIN_DIR`
(defaults to `./brain`). All paths are confined to that folder. `sync` records a
file inventory into shared memory so other apps can see what's in the Brain.

## The web dashboard

`python3 -m skynet serve` starts a zero-dependency web dashboard (stdlib
`http.server`) at http://127.0.0.1:8787 showing live app status, health metrics,
and the pending bridge queue. The data comes from `dashboard_data(brain)` over the
same registry + memory; the page auto-refreshes every 15s.

## How commands flow

```
skynet health log weight 190
  └▶ CLI parses ──▶ brain.dispatch("health", "log", {...})
        └▶ registry says health is live ──▶ HealthApp.cmd_log(...)
              └▶ writes to memory (health/metrics)
              └▶ returns AppResult(events=["health.metric_logged"])
        └▶ brain.emit("health.metric_logged") ──▶ matching event rules run
```

## Extending Skynet

1. **Add an app to the catalogue:** add an entry to `registry/apps.json`.
2. **Make it live:** create `skynet/apps/<name>.py` with a `BaseApp` subclass and
   `cmd_<command>` methods, then set the registry entry's `status` to `live` and
   `location` to `skynet.apps.<name>:<Class>`.
3. **Add an automation:** add a rule to `automations/rules.json`.
4. **Run checks on a schedule:** wire `skynet check` to a daily cron or a
   Claude Code Routine.

## Roadmap ideas

- Bridge more apps (Selections, Punch List) onto the queue.
- A **native Drive API** path for `brain_notes` so it works even without Drive
  Desktop file sync (currently it reads the synced local folder).
- Richer automations: schedules, thresholds on any metric, cross-app rules
  (e.g. "job signed → queue a Subtext follow-up → note it in the Brain").
- Auth on the dashboard if it's ever exposed beyond localhost.
