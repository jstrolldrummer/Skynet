// Dropbox API client for the Skynet connector.
//
// Auth: supports two modes, picked automatically from the environment.
//   1. Short-lived access token:   DROPBOX_ACCESS_TOKEN
//   2. Long-lived refresh token:   DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET
//      (preferred — the client exchanges it for a fresh access token automatically,
//       so the connector keeps working past the 4-hour access-token expiry.)
//
// Everything here uses the global fetch in Node 18+, so there are no runtime deps.

const RPC = "https://api.dropboxapi.com/2";
const CONTENT = "https://content.dropboxapi.com/2";
const OAUTH_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token";

export class DropboxError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = "DropboxError";
    this.status = status;
    this.body = body;
  }
}

export class DropboxClient {
  constructor(env = process.env) {
    this.accessToken = env.DROPBOX_ACCESS_TOKEN || null;
    this.refreshToken = env.DROPBOX_REFRESH_TOKEN || null;
    this.appKey = env.DROPBOX_APP_KEY || null;
    this.appSecret = env.DROPBOX_APP_SECRET || null;
    this._tokenExpiry = 0; // epoch ms; 0 = unknown

    if (!this.accessToken && !this.refreshToken) {
      throw new DropboxError(
        "No Dropbox credentials. Set DROPBOX_ACCESS_TOKEN, or " +
          "DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET."
      );
    }
  }

  // Normalize a user-facing path into what the Dropbox API expects.
  // The Dropbox root is the empty string ""; "/" and "" both mean root here.
  static normalizePath(p) {
    if (!p || p === "/" || p === ".") return "";
    let out = p.trim().replace(/\\/g, "/");
    if (!out.startsWith("/")) out = "/" + out;
    out = out.replace(/\/+$/, ""); // strip trailing slashes
    return out;
  }

  async _ensureAccessToken() {
    if (this.accessToken && Date.now() < this._tokenExpiry - 60_000) {
      return this.accessToken;
    }
    // If we only have a static access token (no refresh creds), just use it.
    if (!this.refreshToken) return this.accessToken;
    if (!this.appKey || !this.appSecret) {
      throw new DropboxError(
        "DROPBOX_REFRESH_TOKEN is set but DROPBOX_APP_KEY / DROPBOX_APP_SECRET are missing."
      );
    }

    const basic = Buffer.from(`${this.appKey}:${this.appSecret}`).toString("base64");
    const params = new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: this.refreshToken,
    });
    const res = await fetch(OAUTH_TOKEN_URL, {
      method: "POST",
      headers: {
        Authorization: `Basic ${basic}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params,
    });
    const text = await res.text();
    if (!res.ok) {
      throw new DropboxError(`Token refresh failed (HTTP ${res.status})`, {
        status: res.status,
        body: text,
      });
    }
    const data = JSON.parse(text);
    this.accessToken = data.access_token;
    this._tokenExpiry = Date.now() + (data.expires_in ?? 14400) * 1000;
    return this.accessToken;
  }

  async _rpc(endpoint, args) {
    const token = await this._ensureAccessToken();
    const res = await fetch(`${RPC}${endpoint}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      // Dropbox treats a null body as "no args"; some endpoints want no body at all.
      body: args === undefined ? undefined : JSON.stringify(args),
    });
    const text = await res.text();
    if (!res.ok) {
      throw new DropboxError(`Dropbox RPC ${endpoint} failed (HTTP ${res.status})`, {
        status: res.status,
        body: text,
      });
    }
    return text ? JSON.parse(text) : {};
  }

  // ---- Read operations -----------------------------------------------------

  /** List a folder's entries, transparently following pagination cursors. */
  async listFolder(path = "", { recursive = false, limit } = {}) {
    const first = await this._rpc("/files/list_folder", {
      path: DropboxClient.normalizePath(path),
      recursive,
      include_non_downloadable_files: true,
    });
    let entries = first.entries;
    let cursor = first.cursor;
    let hasMore = first.has_more;
    while (hasMore && (!limit || entries.length < limit)) {
      const next = await this._rpc("/files/list_folder/continue", { cursor });
      entries = entries.concat(next.entries);
      cursor = next.cursor;
      hasMore = next.has_more;
    }
    return limit ? entries.slice(0, limit) : entries;
  }

  /** Metadata for a single file or folder. */
  async getMetadata(path) {
    return this._rpc("/files/get_metadata", {
      path: DropboxClient.normalizePath(path),
    });
  }

  /** Download a file. Returns { metadata, buffer }. */
  async download(path) {
    const token = await this._ensureAccessToken();
    const res = await fetch(`${CONTENT}/files/download`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Dropbox-API-Arg": JSON.stringify({ path: DropboxClient.normalizePath(path) }),
      },
    });
    if (!res.ok) {
      const body = await res.text();
      throw new DropboxError(`Download failed (HTTP ${res.status})`, {
        status: res.status,
        body,
      });
    }
    const apiResult = res.headers.get("dropbox-api-result");
    const buffer = Buffer.from(await res.arrayBuffer());
    return { metadata: apiResult ? JSON.parse(apiResult) : null, buffer };
  }

  /** Download a file as UTF-8 text. */
  async readText(path) {
    const { metadata, buffer } = await this.download(path);
    return { metadata, text: buffer.toString("utf8") };
  }

  /** Search for files/folders by name or content. */
  async search(query, { path = "", maxResults = 25 } = {}) {
    const options = { max_results: maxResults };
    const p = DropboxClient.normalizePath(path);
    if (p) options.path = p;
    const res = await this._rpc("/files/search_v2", { query, options });
    return res.matches ?? [];
  }

  /** Verify credentials; returns the current account. */
  async whoAmI() {
    return this._rpc("/users/get_current_account", null);
  }

  // ---- Write operations (opt-in; require *.write scopes) -------------------

  /** Upload/overwrite a file from a Buffer or string. */
  async upload(path, contents, { mode = "overwrite" } = {}) {
    const token = await this._ensureAccessToken();
    const body = Buffer.isBuffer(contents) ? contents : Buffer.from(String(contents), "utf8");
    const res = await fetch(`${CONTENT}/files/upload`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": JSON.stringify({
          path: DropboxClient.normalizePath(path),
          mode,
          autorename: false,
          mute: true,
        }),
      },
      body,
    });
    const text = await res.text();
    if (!res.ok) {
      throw new DropboxError(`Upload failed (HTTP ${res.status})`, {
        status: res.status,
        body: text,
      });
    }
    return JSON.parse(text);
  }
}
