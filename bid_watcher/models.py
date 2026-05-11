from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Attachment:
    filename: str
    mime_type: str
    content: bytes


@dataclass
class IncomingEmail:
    source: Literal["gmail", "outlook"]
    message_id: str            # Provider-native id, stable per message
    thread_id: Optional[str]
    account_email: str         # The watched mailbox that received it
    sender_name: Optional[str]
    sender_email: str
    subject: str
    body_text: str
    body_html: Optional[str]
    received_at: datetime
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class BidClassification:
    is_bid_request: bool
    confidence: float          # 0..1
    client_company: Optional[str]
    contact_name: Optional[str]
    project_name: Optional[str]
    project_location: Optional[str]
    due_date: Optional[str]    # ISO date if extractable, else None
    scope_summary: str         # Empty string when not a bid
    trades: list[str] = field(default_factory=list)
    notes: Optional[str] = None
