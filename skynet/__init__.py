"""Skynet — the master brain for Joe Gray's Wyatt & Gray apps.

Skynet is the *active* coordination layer over the apps and functions built in
Cowork. It has four simple parts:

    registry     — the list of every app and the functions each exposes
    memory       — one shared source of truth every app reads and writes
    automations  — "when X happens, do Y" rules across apps
    brain        — the orchestrator that ties them together and routes commands

The public surface is small on purpose:

    from skynet import Brain
    brain = Brain.default()
    brain.status()
"""

from .brain import Brain
from .memory import MemoryStore
from .registry import Registry, App
from .automations import Automations, Rule
from .apps.base import BaseApp, AppResult

__all__ = [
    "Brain",
    "MemoryStore",
    "Registry",
    "App",
    "Automations",
    "Rule",
    "BaseApp",
    "AppResult",
]

__version__ = "0.1.0"
