# Skynet

A personal AI that lives on your own hardware. Mac runs the model and stores conversations; iPhone/iPad talk to it over Tailscale.

```
[iPhone / iPad — SwiftUI app]
            │  HTTPS over Tailscale (or LAN)
            ▼
[Mac mini / desktop]
   ├── Skynet server (FastAPI, port 8080)
   ├── Ollama (local LLM)
   └── SQLite (conversations.db)
```

## Mac setup

1. **Install Ollama** and pull a model:
   ```bash
   brew install ollama
   ollama serve &
   ollama pull llama3.1:8b
   ```

2. **Run the Skynet server**:
   ```bash
   cd server
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   cp .env.example .env
   # edit .env: set AUTH_TOKEN to a long random string (e.g. `openssl rand -hex 32`)
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

3. **Auto-start on boot** (optional): wrap step 2 in a `launchd` plist under `~/Library/LaunchAgents/`.

## Tailscale

Install Tailscale on the Mac and on each iPhone/iPad. The Mac will be reachable at something like `your-mac.tail-XXXX.ts.net`. No port forwarding, no public exposure.

Traffic on the tailnet is already WireGuard-encrypted, so plain HTTP over Tailscale is safe between your own devices.

## iOS app

1. Open Xcode → **File → New → Project → iOS App**. Name it `Skynet`, interface `SwiftUI`, language `Swift`, minimum iOS 17.
2. Delete the generated `ContentView.swift` and `SkynetApp.swift`.
3. Drag every `.swift` file from `ios/Skynet/` into the project's `Skynet` group (check **Copy items if needed**).
4. Build & run on device. In the app, tap the gear icon and enter:
   - **Server URL**: `http://your-mac.tail-XXXX.ts.net:8080`
   - **Auth token**: the value of `AUTH_TOKEN` from `server/.env`
5. Tap **Test connection** → should say `Connected`. Hit the compose icon to start a chat.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Public liveness check |
| `GET` | `/conversations` | List, newest first |
| `POST` | `/conversations` | `{title}` |
| `PATCH` | `/conversations/{id}` | `{title}` |
| `DELETE` | `/conversations/{id}` | |
| `GET` | `/conversations/{id}/messages` | |
| `POST` | `/chat` | `{conversation_id, content}` → SSE stream of `delta` / `done` / `error` events |

All non-`/health` endpoints require `Authorization: Bearer <AUTH_TOKEN>`.

## Roadmap

- v0.1 (this): text chat with persistent history
- next: RAG over personal files; tool use (shell, calendar, mail); voice in/out via Whisper + on-device TTS; optional Claude/OpenAI fallback for hard queries
