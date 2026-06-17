# Skynet Dropbox Connector

A Dropbox connector for the Skynet master brain. Ships in two forms that share
one client (`src/client.js`):

- **MCP server** (`src/server.js`) — exposes Dropbox as MCP tools for Claude Code
  and other MCP clients. Registered in the repo-root `.mcp.json`.
- **CLI** (`src/cli.js`) — direct command-line access for scripts and bulk pulls.

## 1. Get credentials

1. Go to <https://www.dropbox.com/developers/apps> → **Create app**.
2. **Scoped access** → **Full Dropbox** (so it can see `/apps/...`).
3. **Permissions** tab: enable `files.metadata.read` and `files.content.read`
   (add `files.content.write` if you want Skynet to write back). Click **Submit**.
4. **Settings** tab:
   - For a quick start: **Generate** an access token (valid ~4 hours).
   - For a permanent setup: use the App key/secret to run the OAuth "offline"
     flow once and capture a **refresh token** (recommended — auto-refreshes).

## 2. Provide credentials

Set them as environment variables / session secrets (preferred), or copy
`.env.example` to `.env`:

```bash
# quick start
export DROPBOX_ACCESS_TOKEN="sl.xxx..."

# or permanent
export DROPBOX_REFRESH_TOKEN="..."
export DROPBOX_APP_KEY="..."
export DROPBOX_APP_SECRET="..."
```

## 3. Use it

### CLI

```bash
cd connectors/dropbox
npm install

node src/cli.js whoami
node src/cli.js ls /apps
node src/cli.js tree /apps/dropbox
node src/cli.js cat /apps/dropbox/foreman/index.html
node src/cli.js pull /apps/dropbox/foreman ./_pulled/foreman   # mirror locally
node src/cli.js search foreman
```

### MCP (Claude Code)

The repo-root `.mcp.json` registers this server as `skynet-dropbox`. With the
env vars set, start a Claude Code session and these tools become available:

| Tool | Purpose |
| --- | --- |
| `dropbox_whoami` | verify credentials / show account |
| `dropbox_list_folder` | list a folder (optionally recursive) |
| `dropbox_read_file` | read a text file |
| `dropbox_get_metadata` | metadata for one path |
| `dropbox_search` | search by name/content |
| `dropbox_upload` | write a text file (needs write scope) |

## Notes

- Dropbox paths are absolute and case-insensitive; the root is `""` (empty) —
  the client accepts `/`, `""`, or any `/foo/bar` path.
- No third-party runtime deps in the client (uses Node 18+ global `fetch`);
  the MCP server uses `@modelcontextprotocol/sdk` + `zod`.
