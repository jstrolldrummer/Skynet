import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/app.js';

// Spin the app up on an ephemeral port and return its base URL + a closer.
async function startApp() {
  const app = createApp();
  const server = await new Promise((resolve) => {
    const s = app.listen(0, () => resolve(s));
  });
  const { port } = server.address();
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

test('GET /health returns ok', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/health`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: 'ok' });
  } finally {
    await close();
  }
});

test('unknown route returns 404 JSON', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/nope`);
    assert.equal(res.status, 404);
    const body = await res.json();
    assert.equal(body.error.message, 'Not found');
  } finally {
    await close();
  }
});

test('metadata without path returns 400', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/api/files/metadata`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    assert.equal(res.status, 400);
    const body = await res.json();
    assert.match(body.error.message, /path/);
  } finally {
    await close();
  }
});

test('search without query returns 400', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/api/files/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    assert.equal(res.status, 400);
  } finally {
    await close();
  }
});

test('move without paths returns 400', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/api/files/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_path: '/a.txt' }),
    });
    assert.equal(res.status, 400);
  } finally {
    await close();
  }
});

test('download without path returns 400', async () => {
  const { baseUrl, close } = await startApp();
  try {
    const res = await fetch(`${baseUrl}/api/files/download`);
    assert.equal(res.status, 400);
  } finally {
    await close();
  }
});
