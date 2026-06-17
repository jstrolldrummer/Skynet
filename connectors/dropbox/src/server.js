#!/usr/bin/env node
// Skynet Dropbox MCP server (stdio transport).
//
// Exposes Dropbox as MCP tools so any MCP client (Claude Code, etc.) can browse
// and read your Dropbox. Register it in .mcp.json (see repo root) and provide
// credentials via env (see client.js).
//
// Tools:
//   dropbox_whoami        verify credentials / show account
//   dropbox_list_folder   list entries in a folder
//   dropbox_read_file     read a text file's contents
//   dropbox_get_metadata  metadata for one path
//   dropbox_search        search by name/content
//   dropbox_upload        write a text file (requires *.write scope)

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { DropboxClient, DropboxError } from "./client.js";
import { z as zod } from "zod";

const client = new DropboxClient();

const server = new McpServer({
  name: "skynet-dropbox",
  version: "0.1.0",
});

function ok(text) {
  return { content: [{ type: "text", text }] };
}
function fail(e) {
  const msg = e instanceof DropboxError && e.body ? `${e.message}\n${e.body}` : e.message;
  return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
}

server.tool(
  "dropbox_whoami",
  "Verify Dropbox credentials and show the connected account.",
  {},
  async () => {
    try {
      const me = await client.whoAmI();
      return ok(`${me.name?.display_name} <${me.email}>\naccount_id: ${me.account_id}`);
    } catch (e) {
      return fail(e);
    }
  }
);

server.tool(
  "dropbox_list_folder",
  "List files and folders in a Dropbox folder. Use empty path for the root.",
  {
    path: zod.string().default("").describe("Folder path, e.g. /apps/dropbox. Empty = root."),
    recursive: zod.boolean().default(false).describe("Recurse into subfolders."),
  },
  async ({ path, recursive }) => {
    try {
      const entries = await client.listFolder(path, { recursive });
      const lines = entries.map(
        (e) => `${e[".tag"] === "folder" ? "[dir] " : "[file]"} ${e.path_display}`
      );
      return ok(lines.join("\n") || "(empty)");
    } catch (e) {
      return fail(e);
    }
  }
);

server.tool(
  "dropbox_read_file",
  "Read a text file from Dropbox and return its contents.",
  {
    path: zod.string().describe("Full path to the file, e.g. /apps/dropbox/foreman/app.js"),
  },
  async ({ path }) => {
    try {
      const { text } = await client.readText(path);
      return ok(text);
    } catch (e) {
      return fail(e);
    }
  }
);

server.tool(
  "dropbox_get_metadata",
  "Get metadata (size, type, modified time) for a Dropbox file or folder.",
  { path: zod.string().describe("Full path to the file or folder.") },
  async ({ path }) => {
    try {
      const md = await client.getMetadata(path);
      return ok(JSON.stringify(md, null, 2));
    } catch (e) {
      return fail(e);
    }
  }
);

server.tool(
  "dropbox_search",
  "Search Dropbox for files/folders by name or content.",
  {
    query: zod.string().describe("Search query."),
    path: zod.string().default("").describe("Restrict search to this folder. Empty = everywhere."),
  },
  async ({ query, path }) => {
    try {
      const matches = await client.search(query, { path });
      const lines = matches
        .map((m) => m.metadata?.metadata?.path_display)
        .filter(Boolean);
      return ok(lines.join("\n") || "(no matches)");
    } catch (e) {
      return fail(e);
    }
  }
);

server.tool(
  "dropbox_upload",
  "Write/overwrite a UTF-8 text file in Dropbox. Requires files.content.write scope.",
  {
    path: zod.string().describe("Destination path, e.g. /apps/dropbox/notes.md"),
    contents: zod.string().describe("Text contents to write."),
  },
  async ({ path, contents }) => {
    try {
      const md = await client.upload(path, contents);
      return ok(`Uploaded -> ${md.path_display} (${md.size} bytes)`);
    } catch (e) {
      return fail(e);
    }
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("skynet-dropbox MCP server running on stdio");
