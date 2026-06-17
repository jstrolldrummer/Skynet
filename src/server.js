import { createApp } from './app.js';
import { config, assertConfigured } from './config.js';

assertConfigured();

const app = createApp();

app.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(`Skynet Dropbox API listening on http://localhost:${config.port}`);
});
