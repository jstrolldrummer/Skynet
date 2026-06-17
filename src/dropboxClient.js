import { config } from './config.js';

/**
 * Error thrown when the Dropbox API responds with a non-2xx status.
 * Carries the upstream status code and parsed body so callers (and the
 * Express error handler) can surface a faithful response.
 */
export class DropboxApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = 'DropboxApiError';
    this.status = status;
    this.body = body;
  }
}

function authHeader() {
  return `Bearer ${config.dropboxAccessToken}`;
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) return null;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return text;
}

/**
 * Call an RPC-style endpoint on api.dropboxapi.com.
 * These take a JSON request body and return a JSON response.
 *
 * @param {string} endpoint e.g. '/2/files/list_folder'
 * @param {object|null} args JSON-serializable arguments (null sends no body)
 */
export async function rpc(endpoint, args) {
  const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
    method: 'POST',
    headers: {
      Authorization: authHeader(),
      // Dropbox requires an explicit empty content-type when there is no body.
      'Content-Type': args == null ? '' : 'application/json',
    },
    body: args == null ? undefined : JSON.stringify(args),
  });

  const body = await parseResponse(response);
  if (!response.ok) {
    throw new DropboxApiError(`Dropbox RPC ${endpoint} failed`, {
      status: response.status,
      body,
    });
  }
  return body;
}

/**
 * Upload binary content to content.dropboxapi.com.
 * The endpoint arguments travel in the Dropbox-API-Arg header, the file
 * bytes travel in the request body.
 *
 * @param {string} endpoint e.g. '/2/files/upload'
 * @param {object} args JSON-serializable arguments
 * @param {Buffer|Uint8Array} content raw file bytes
 */
export async function contentUpload(endpoint, args, content) {
  const response = await fetch(`${config.contentBaseUrl}${endpoint}`, {
    method: 'POST',
    headers: {
      Authorization: authHeader(),
      'Dropbox-API-Arg': JSON.stringify(args),
      'Content-Type': 'application/octet-stream',
    },
    body: content,
  });

  const body = await parseResponse(response);
  if (!response.ok) {
    throw new DropboxApiError(`Dropbox content upload ${endpoint} failed`, {
      status: response.status,
      body,
    });
  }
  return body;
}

/**
 * Download binary content from content.dropboxapi.com.
 * Returns the raw bytes plus the parsed Dropbox-API-Result metadata header.
 *
 * @param {string} endpoint e.g. '/2/files/download'
 * @param {object} args JSON-serializable arguments
 * @returns {Promise<{ content: Buffer, metadata: object|null, contentType: string }>}
 */
export async function contentDownload(endpoint, args) {
  const response = await fetch(`${config.contentBaseUrl}${endpoint}`, {
    method: 'POST',
    headers: {
      Authorization: authHeader(),
      'Dropbox-API-Arg': JSON.stringify(args),
    },
  });

  if (!response.ok) {
    const body = await parseResponse(response);
    throw new DropboxApiError(`Dropbox content download ${endpoint} failed`, {
      status: response.status,
      body,
    });
  }

  const resultHeader = response.headers.get('dropbox-api-result');
  const metadata = resultHeader ? JSON.parse(resultHeader) : null;
  const arrayBuffer = await response.arrayBuffer();
  return {
    content: Buffer.from(arrayBuffer),
    metadata,
    contentType:
      response.headers.get('content-type') ?? 'application/octet-stream',
  };
}
