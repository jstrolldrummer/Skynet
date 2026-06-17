# Skynet — Dropbox API

A lightweight Node.js + Express REST API that wraps the [Dropbox HTTP API](https://www.dropbox.com/developers/documentation/http/documentation).
It exposes a small, predictable surface for browsing, uploading, downloading,
and managing files in a Dropbox account.

Requests are proxied to the two Dropbox hosts:

- `api.dropboxapi.com` — RPC endpoints (metadata, list, search, move, etc.)
- `content.dropboxapi.com` — content transfer (upload / download)

## Setup

```bash
npm install
cp .env.example .env   # then fill in DROPBOX_ACCESS_TOKEN
npm start              # or: npm run dev  (auto-reload)
```

Generate an access token from the [Dropbox App Console](https://www.dropbox.com/developers/apps).

| Variable                | Required | Default | Description                       |
| ----------------------- | -------- | ------- | --------------------------------- |
| `DROPBOX_ACCESS_TOKEN`  | yes      | —       | OAuth2 token for the Dropbox app. |
| `PORT`                  | no       | `3000`  | HTTP port to listen on.           |

## Endpoints

All endpoints are prefixed with `/api`. JSON in, JSON out (except download,
which streams raw bytes, and upload, which takes raw bytes).

### Account

| Method | Path             | Description                       |
| ------ | ---------------- | --------------------------------- |
| GET    | `/account`       | Current account info.             |
| GET    | `/account/usage` | Storage space usage.              |

### Files

| Method | Path                  | Description                                              |
| ------ | --------------------- | ------------------------------------------------------- |
| GET    | `/files`              | List a folder. Query: `path`, `recursive`, `limit`.     |
| GET    | `/files/continue`     | Page a listing. Query: `cursor`.                        |
| POST   | `/files/metadata`     | Metadata for one entry. Body: `{ path }`.               |
| POST   | `/files/search`       | Search. Body: `{ query, path?, max_results? }`.         |
| POST   | `/files/folder`       | Create a folder. Body: `{ path, autorename? }`.         |
| POST   | `/files/move`         | Move/rename. Body: `{ from_path, to_path, autorename? }`. |
| POST   | `/files/copy`         | Copy. Body: `{ from_path, to_path, autorename? }`.      |
| DELETE | `/files`              | Delete. Body: `{ path }`.                               |
| POST   | `/files/upload`       | Upload raw bytes. Query: `path`, `mode?`, `autorename?`, `mute?`. Body: file content. |
| GET    | `/files/download`     | Download raw bytes. Query: `path`.                      |

### Health

`GET /health` → `{ "status": "ok" }`

## Examples

```bash
# List the root folder
curl "http://localhost:3000/api/files?path="

# Get metadata for a file
curl -X POST http://localhost:3000/api/files/metadata \
  -H 'Content-Type: application/json' \
  -d '{"path":"/notes.txt"}'

# Upload a file
curl -X POST "http://localhost:3000/api/files/upload?path=/notes.txt&mode=overwrite" \
  --data-binary @notes.txt

# Download a file
curl "http://localhost:3000/api/files/download?path=/notes.txt" -o notes.txt

# Search
curl -X POST http://localhost:3000/api/files/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"report"}'
```

## Errors

Failures from Dropbox are relayed with the upstream status code and body:

```json
{
  "error": {
    "message": "Dropbox RPC /2/files/get_metadata failed",
    "dropbox": { "error_summary": "path/not_found/..." }
  }
}
```

## Tests

```bash
npm test
```

Tests cover health, routing, and request validation; they run without a real
Dropbox token.
