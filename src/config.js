// Centralized configuration loaded from the environment.

export const config = {
  port: Number.parseInt(process.env.PORT ?? '3000', 10),
  dropboxAccessToken: process.env.DROPBOX_ACCESS_TOKEN ?? '',
  // The two hosts the Dropbox HTTP API is split across:
  //   - api.dropboxapi.com      → RPC-style endpoints (JSON in / JSON out)
  //   - content.dropboxapi.com  → content-transfer endpoints (upload / download)
  apiBaseUrl: 'https://api.dropboxapi.com',
  contentBaseUrl: 'https://content.dropboxapi.com',
};

export function assertConfigured() {
  if (!config.dropboxAccessToken) {
    throw new Error(
      'DROPBOX_ACCESS_TOKEN is not set. Copy .env.example to .env and provide a token.',
    );
  }
}
