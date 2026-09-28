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

- **live** — an in-process adapter that actually runs here (e.g. **Health**).
  Registry `location` points to `module:Class`; the brain loads and calls it.
- **external** — apps that run on Joe's Mac or in Cowork (Foreman, Subtext,
  Selections, Punch List). Skynet can't execute them directly, so a command
  returns an **intent** (what should happen) and coordinates through shared
  memory instead of pretending to run them.
- **planned** — not built yet.

This is the key design choice: rather than fake control over apps it can't reach,
Skynet is a **shared brain + coordinator**. Any app that writes to Skynet's memory
(or that we build a live adapter / bridge for) becomes controllable and can share
state with every other app.

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

- A **Google Drive bridge** so the `brain_notes` app can read/update the Drive
  Brain markdown files directly (Drive is already connected).
- Bridge adapters for **Foreman/Subtext** (e.g. write a "follow-up requested"
  record to memory that the Mac side polls).
- A small **web dashboard** over the same registry + memory.
