import express from 'express';
import { filesRouter } from './routes/files.js';
import { accountRouter } from './routes/account.js';
import { DropboxApiError } from './dropboxClient.js';

export function createApp() {
  const app = express();

  // JSON body parsing for RPC-style routes. The upload route opts into raw
  // parsing locally, so a generous default here is fine.
  app.use(express.json());

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok' });
  });

  app.use('/api', accountRouter);
  app.use('/api', filesRouter);

  // 404 for anything unmatched.
  app.use((_req, res) => {
    res.status(404).json({ error: { message: 'Not found' } });
  });

  // Centralized error handler. Faithfully relays Dropbox failures.
  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    if (err instanceof DropboxApiError) {
      return res.status(err.status ?? 502).json({
        error: {
          message: err.message,
          dropbox: err.body,
        },
      });
    }
    const status = err.status ?? 500;
    res.status(status).json({ error: { message: err.message } });
  });

  return app;
}
