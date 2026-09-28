"""Brain Notes — a live bridge to Joe's Drive-synced 'Brain' markdown folder.

Joe keeps a passive-memory "Brain" (MASTER.md, me.md, contracting/, finance/,
health/, personal/) that Google Drive Desktop syncs to a local folder. This app
lets Skynet read, search, and append to those files, and pull a file inventory
into shared memory — so the active brain and the passive brain stay connected.

Point it at the folder with the SKYNET_BRAIN_DIR environment variable (see
skynet/config.py). All paths are confined to that folder (no traversal out).

Commands:
    list                list markdown files in the Brain
    read <path>         print a file's contents      (path relative to Brain dir)
    search <query>      find files containing text
    append <path> <text>  append a dated line/section to a file
    sync                record a file inventory into memory (namespace "brain")
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .. import config
from .base import AppResult, BaseApp


class BrainNotesApp(BaseApp):
    id = "brain_notes"

    # -- helpers --------------------------------------------------------------

    def _root(self) -> Path:
        return config.brain_dir()

    def _resolve(self, rel: str) -> Path | None:
        """Resolve a user path inside the Brain dir, or None if it escapes."""
        root = self._root().resolve()
        target = (root / rel).resolve()
        if root == target or root in target.parents:
            return target
        return None

    # -- commands -------------------------------------------------------------

    def cmd_list(self) -> AppResult:
        root = self._root()
        if not root.exists():
            return AppResult.fail(
                f"Brain folder not found: {root}. Set SKYNET_BRAIN_DIR to your "
                "Google Drive Brain path."
            )
        files = sorted(
            str(p.relative_to(root)) for p in root.rglob("*.md") if p.is_file()
        )
        body = "\n".join(f"  {f}" for f in files) or "  (no markdown files)"
        return AppResult.done(f"{len(files)} file(s) in {root}:\n{body}", files=files)

    def cmd_read(self, path: str) -> AppResult:
        target = self._resolve(path)
        if target is None:
            return AppResult.fail(f"Path escapes the Brain folder: {path!r}")
        if not target.exists() or not target.is_file():
            return AppResult.fail(f"Not found: {path}")
        text = target.read_text(encoding="utf-8")
        return AppResult.done(text, path=path, chars=len(text))

    def cmd_search(self, query: str) -> AppResult:
        root = self._root()
        if not root.exists():
            return AppResult.fail(f"Brain folder not found: {root}.")
        q = query.lower()
        hits = []
        for p in root.rglob("*.md"):
            if not p.is_file():
                continue
            try:
                if q in p.read_text(encoding="utf-8").lower():
                    hits.append(str(p.relative_to(root)))
            except (OSError, UnicodeDecodeError):
                continue
        body = "\n".join(f"  {h}" for h in sorted(hits)) or "  (no matches)"
        return AppResult.done(f"{len(hits)} file(s) match {query!r}:\n{body}", matches=hits)

    def cmd_append(self, path: str, text: str) -> AppResult:
        target = self._resolve(path)
        if target is None:
            return AppResult.fail(f"Path escapes the Brain folder: {path!r}")
        if not target.exists():
            return AppResult.fail(
                f"Not found: {path} (create it in the Brain first to be safe)."
            )
        stamped = f"\n- {date.today().isoformat()}: {text}\n"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(stamped)
        return AppResult(
            ok=True,
            summary=f"Appended a dated note to {path}.",
            data={"path": path, "added": stamped.strip()},
            events=[{"name": "brain.note_appended", "payload": {"path": path}}],
        )

    def cmd_sync(self) -> AppResult:
        """Record a file inventory into shared memory so other apps can see it."""
        listed = self.cmd_list()
        if not listed.ok:
            return listed
        files = listed.data["files"]
        self.memory.set("brain", "files", files)
        self.memory.set("brain", "dir", str(self._root()))
        return AppResult.done(
            f"Synced inventory of {len(files)} Brain file(s) into memory "
            "(namespace 'brain').",
            files=files,
        )
