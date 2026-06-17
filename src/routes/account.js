import express from 'express';
import { rpc } from '../dropboxClient.js';

export const accountRouter = express.Router();

const wrap = (handler) => (req, res, next) =>
  Promise.resolve(handler(req, res, next)).catch(next);

/**
 * GET /api/account
 * Information about the account associated with the access token.
 */
accountRouter.get(
  '/account',
  wrap(async (_req, res) => {
    // current_account takes no arguments; Dropbox requires a null body here.
    const result = await rpc('/2/users/get_current_account', null);
    res.json(result);
  }),
);

/**
 * GET /api/account/usage
 * Storage space usage for the account.
 */
accountRouter.get(
  '/account/usage',
  wrap(async (_req, res) => {
    const result = await rpc('/2/users/get_space_usage', null);
    res.json(result);
  }),
);
