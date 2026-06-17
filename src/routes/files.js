import express from 'express';
import {
  rpc,
  contentUpload,
  contentDownload,
} from '../dropboxClient.js';

export const filesRouter = express.Router();

// Wrap async handlers so rejected promises reach the Express error handler.
const wrap = (handler) => (req, res, next) =>
  Promise.resolve(handler(req, res, next)).catch(next);

function requirePath(body) {
  if (typeof body?.path !== 'string' || body.path.length === 0) {
    const err = new Error('A non-empty "path" is required.');
    err.status = 400;
    throw err;
  }
  return body.path;
}

/**
 * GET /api/files?path=/folder&recursive=false
 * List the contents of a folder. Use path="" for the root.
 */
filesRouter.get(
  '/files',
  wrap(async (req, res) => {
    const path = req.query.path ?? '';
    const recursive = req.query.recursive === 'true';
    const limit = req.query.limit ? Number.parseInt(req.query.limit, 10) : undefined;
    const result = await rpc('/2/files/list_folder', {
      path,
      recursive,
      ...(limit ? { limit } : {}),
    });
    res.json(result);
  }),
);

/**
 * GET /api/files/continue?cursor=...
 * Page through a large folder listing using a cursor from a prior response.
 */
filesRouter.get(
  '/files/continue',
  wrap(async (req, res) => {
    const cursor = req.query.cursor;
    if (!cursor) {
      const err = new Error('A "cursor" query parameter is required.');
      err.status = 400;
      throw err;
    }
    const result = await rpc('/2/files/list_folder/continue', { cursor });
    res.json(result);
  }),
);

/**
 * POST /api/files/metadata  { "path": "/folder/file.txt" }
 * Fetch metadata for a single file or folder.
 */
filesRouter.post(
  '/files/metadata',
  wrap(async (req, res) => {
    const path = requirePath(req.body);
    const result = await rpc('/2/files/get_metadata', { path });
    res.json(result);
  }),
);

/**
 * POST /api/files/search  { "query": "report", "path": "" }
 * Search for files and folders.
 */
filesRouter.post(
  '/files/search',
  wrap(async (req, res) => {
    const query = req.body?.query;
    if (typeof query !== 'string' || query.length === 0) {
      const err = new Error('A non-empty "query" is required.');
      err.status = 400;
      throw err;
    }
    const options = {};
    if (typeof req.body.path === 'string') options.path = req.body.path;
    if (req.body.max_results) options.max_results = req.body.max_results;
    const result = await rpc('/2/files/search_v2', {
      query,
      ...(Object.keys(options).length ? { options } : {}),
    });
    res.json(result);
  }),
);

/**
 * POST /api/files/folder  { "path": "/new-folder" }
 * Create a folder.
 */
filesRouter.post(
  '/files/folder',
  wrap(async (req, res) => {
    const path = requirePath(req.body);
    const result = await rpc('/2/files/create_folder_v2', {
      path,
      autorename: Boolean(req.body.autorename),
    });
    res.status(201).json(result);
  }),
);

/**
 * POST /api/files/move  { "from_path": "/a.txt", "to_path": "/b.txt" }
 * Move (or rename) a file or folder.
 */
filesRouter.post(
  '/files/move',
  wrap(async (req, res) => {
    const { from_path, to_path } = req.body ?? {};
    if (!from_path || !to_path) {
      const err = new Error('Both "from_path" and "to_path" are required.');
      err.status = 400;
      throw err;
    }
    const result = await rpc('/2/files/move_v2', {
      from_path,
      to_path,
      autorename: Boolean(req.body.autorename),
    });
    res.json(result);
  }),
);

/**
 * POST /api/files/copy  { "from_path": "/a.txt", "to_path": "/b.txt" }
 * Copy a file or folder.
 */
filesRouter.post(
  '/files/copy',
  wrap(async (req, res) => {
    const { from_path, to_path } = req.body ?? {};
    if (!from_path || !to_path) {
      const err = new Error('Both "from_path" and "to_path" are required.');
      err.status = 400;
      throw err;
    }
    const result = await rpc('/2/files/copy_v2', {
      from_path,
      to_path,
      autorename: Boolean(req.body.autorename),
    });
    res.json(result);
  }),
);

/**
 * DELETE /api/files  { "path": "/folder/file.txt" }
 * Delete a file or folder.
 */
filesRouter.delete(
  '/files',
  wrap(async (req, res) => {
    const path = requirePath(req.body);
    const result = await rpc('/2/files/delete_v2', { path });
    res.json(result);
  }),
);

/**
 * POST /api/files/upload?path=/folder/file.bin&mode=add
 * Upload raw bytes (request body is the file content).
 */
filesRouter.post(
  '/files/upload',
  express.raw({ type: '*/*', limit: '150mb' }),
  wrap(async (req, res) => {
    const path = req.query.path;
    if (!path) {
      const err = new Error('A "path" query parameter is required.');
      err.status = 400;
      throw err;
    }
    if (!req.body || req.body.length === 0) {
      const err = new Error('Request body (file content) is empty.');
      err.status = 400;
      throw err;
    }
    const result = await contentUpload(
      '/2/files/upload',
      {
        path,
        mode: req.query.mode ?? 'add',
        autorename: req.query.autorename === 'true',
        mute: req.query.mute === 'true',
      },
      req.body,
    );
    res.status(201).json(result);
  }),
);

/**
 * GET /api/files/download?path=/folder/file.bin
 * Stream a file's bytes back to the caller.
 */
filesRouter.get(
  '/files/download',
  wrap(async (req, res) => {
    const path = req.query.path;
    if (!path) {
      const err = new Error('A "path" query parameter is required.');
      err.status = 400;
      throw err;
    }
    const { content, metadata, contentType } = await contentDownload(
      '/2/files/download',
      { path },
    );
    if (metadata?.name) {
      res.setHeader(
        'Content-Disposition',
        `attachment; filename="${encodeURIComponent(metadata.name)}"`,
      );
    }
    res.setHeader('Content-Type', contentType);
    res.send(content);
  }),
);
