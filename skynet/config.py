"""Small configuration helpers for Skynet.

Paths that depend on the machine Skynet runs on live here, resolved from
environment variables with sensible defaults so nothing is hard-coded.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def brain_dir() -> Path:
    """Where the Drive-synced 'Brain' markdown folder lives.

    On Joe's Mac this is the Google Drive Desktop path, e.g.
        ~/Library/CloudStorage/GoogleDrive-joe@wyattgrayhomes.com/My Drive/Apps/Brain
    Set SKYNET_BRAIN_DIR to point at it. Falls back to a local ./brain folder so
    the app is usable (and testable) with no configuration.
    """
    env = os.environ.get("SKYNET_BRAIN_DIR")
    if env:
        return Path(env).expanduser()
    return _REPO_ROOT / "brain"
