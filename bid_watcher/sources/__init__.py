from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from bid_watcher.models import IncomingEmail


class EmailSource(ABC):
    """An inbox that can be polled for new messages received after a timestamp."""

    name: str

    @abstractmethod
    def fetch_since(self, since: datetime) -> Iterable[IncomingEmail]:
        """Yield emails received strictly after `since`. Implementations must include attachments."""
