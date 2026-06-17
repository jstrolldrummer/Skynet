#!/usr/bin/env node
// Skynet Dropbox CLI — direct access to Dropbox without the MCP layer.
// Useful for scripts, debugging, and bulk-pulling folders into the workspace.
//
// Usage:
//   skynet-dropbox whoami
//   skynet-dropbox ls [path] [--recursive]
//   skynet-dropbox tree [path]
//   skynet-dropbox cat <path>
//   skynet-dropbox get <path> [localPath]
//   skynet-dropbox pull <dropboxFolder> <localDir>   # mirror a folder locally
//   skynet-dropbox search <query> [path]
//
// Credentials come from the environment (see client.js).

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { DropboxClient, DropboxError } from "./client.js";

function fmtSize(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)}${u[i]}`;
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const flags = new Set(rest.filter((a) => a.startsWith("--")));
  const args = rest.filter((a) => !a.startsWith("--"));

  const HELP = [
    "Skynet Dropbox CLI",
    "",
    "Commands:",
    "  whoami                          verify credentials",
    "  ls [path] [--recursive]         list a folder",
    "  tree [path]                     recursive indented listing",
    "  cat <path>                      print a text file",
    "  get <path> [localPath]          download one file",
    "  pull <dropboxFolder> <localDir> mirror a folder locally",
    "  search <query> [path]           search files",
  ].join("\n");

  if (!cmd || cmd === "help" || cmd === "--help" || cmd === "-h") {
    console.log(HELP);
    return;
  }

  let client;
  try {
    client = new DropboxClient();
  } catch (e) {
    console.error(`✗ ${e.message}`);
    process.exit(2);
  }

  switch (cmd) {
    case "whoami": {
      const me = await client.whoAmI();
      console.log(`${me.name?.display_name} <${me.email}>`);
      console.log(`account_id: ${me.account_id}`);
      break;
    }

    case "ls": {
      const entries = await client.listFolder(args[0] ?? "", {
        recursive: flags.has("--recursive"),
      });
      for (const e of entries) {
        const tag = e[".tag"] === "folder" ? "d" : "-";
        const size = e[".tag"] === "file" ? fmtSize(e.size) : "";
        console.log(`${tag}  ${size.padStart(8)}  ${e.path_display}`);
      }
      console.log(`\n${entries.length} ent ${entries.length === 1 ? "ry" : "ries"}`);
      break;
    }

    case "tree": {
      const entries = await client.listFolder(args[0] ?? "", { recursive: true });
      entries.sort((a, b) => a.path_lower.localeCompare(b.path_lower));
      for (const e of entries) {
        const depth = (e.path_display.match(/\//g) || []).length - 1;
        const name = e.name + (e[".tag"] === "folder" ? "/" : "");
        console.log("  ".repeat(Math.max(0, depth)) + name);
      }
      break;
    }

    case "cat": {
      if (!args[0]) throw new Error("usage: cat <path>");
      const { text } = await client.readText(args[0]);
      process.stdout.write(text);
      break;
    }

    case "get": {
      if (!args[0]) throw new Error("usage: get <path> [localPath]");
      const { metadata, buffer } = await client.download(args[0]);
      const local = args[1] ?? metadata?.name ?? "download.bin";
      await mkdir(dirname(local), { recursive: true });
      await writeFile(local, buffer);
      console.log(`✓ saved ${fmtSize(buffer.length)} -> ${local}`);
      break;
    }

    case "pull": {
      if (!args[0] || !args[1]) throw new Error("usage: pull <dropboxFolder> <localDir>");
      const [folder, localDir] = args;
      const entries = await client.listFolder(folder, { recursive: true });
      const base = DropboxClient.normalizePath(folder);
      let files = 0;
      for (const e of entries) {
        if (e[".tag"] !== "file") continue;
        const rel = e.path_lower.startsWith(base.toLowerCase())
          ? e.path_display.slice(base.length).replace(/^\//, "")
          : e.path_display.replace(/^\//, "");
        const dest = join(localDir, rel);
        const { buffer } = await client.download(e.path_display);
        await mkdir(dirname(dest), { recursive: true });
        await writeFile(dest, buffer);
        files++;
        console.log(`  ✓ ${rel} (${fmtSize(buffer.length)})`);
      }
      console.log(`\n✓ pulled ${files} file(s) -> ${localDir}`);
      break;
    }

    case "search": {
      if (!args[0]) throw new Error("usage: search <query> [path]");
      const matches = await client.search(args[0], { path: args[1] ?? "" });
      for (const m of matches) {
        const md = m.metadata?.metadata;
        if (md) console.log(`${md[".tag"] === "folder" ? "d" : "-"}  ${md.path_display}`);
      }
      console.log(`\n${matches.length} match(es)`);
      break;
    }

    default:
      console.error(`Unknown command: ${cmd}\n`);
      console.log(HELP);
      process.exit(1);
  }
}

main().catch((e) => {
  if (e instanceof DropboxError) {
    console.error(`✗ ${e.message}`);
    if (e.body) console.error(e.body);
  } else {
    console.error(`✗ ${e.stack || e.message}`);
  }
  process.exit(1);
});
