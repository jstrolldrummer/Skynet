from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from bid_watcher.config import load_settings
from bid_watcher.models import Attachment, IncomingEmail
from bid_watcher.sources import EmailSource
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _load_creds(client_secret_file: Path, token_file: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())
    return creds


def _walk_parts(payload: dict):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _decode_body(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class GmailSource(EmailSource):
    name = "gmail"

    def __init__(self, client_secret_file: Path, token_file: Path, account_email: str) -> None:
        self.account_email = account_email
        self._creds = _load_creds(client_secret_file, token_file)
        self._svc = build("gmail", "v1", credentials=self._creds, cache_discovery=False)

    def fetch_since(self, since: datetime) -> Iterable[IncomingEmail]:
        after_epoch = int(since.timestamp())
        query = f"has:attachment after:{after_epoch}"
        page_token = None
        while True:
            resp = (
                self._svc.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token, maxResults=50)
                .execute()
            )
            for meta in resp.get("messages", []) or []:
                msg = self._svc.users().messages().get(userId="me", id=meta["id"], format="full").execute()
                email = self._convert(msg)
                if email is not None and email.received_at > since:
                    yield email
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def _convert(self, msg: dict) -> Optional[IncomingEmail]:
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_header = headers.get("from", "")
        sender_name, sender_email = parseaddr(from_header)
        subject = headers.get("subject", "")
        date_hdr = headers.get("date")
        try:
            received_at = parsedate_to_datetime(date_hdr) if date_hdr else datetime.fromtimestamp(
                int(msg["internalDate"]) / 1000, tz=timezone.utc
            )
        except (TypeError, ValueError):
            received_at = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        body_text = ""
        body_html: Optional[str] = None
        attachments: list[Attachment] = []

        for part in _walk_parts(msg.get("payload", {})):
            mime = part.get("mimeType", "")
            filename = part.get("filename") or ""
            body = part.get("body", {}) or {}
            if filename and (body.get("attachmentId") or body.get("data")):
                if body.get("attachmentId"):
                    att = (
                        self._svc.users()
                        .messages()
                        .attachments()
                        .get(userId="me", messageId=msg["id"], id=body["attachmentId"])
                        .execute()
                    )
                    content = _decode_body(att["data"])
                else:
                    content = _decode_body(body["data"])
                attachments.append(Attachment(filename=filename, mime_type=mime, content=content))
            elif mime == "text/plain" and body.get("data") and not body_text:
                body_text = _decode_body(body["data"]).decode("utf-8", errors="replace")
            elif mime == "text/html" and body.get("data") and not body_html:
                body_html = _decode_body(body["data"]).decode("utf-8", errors="replace")

        return IncomingEmail(
            source="gmail",
            message_id=msg["id"],
            thread_id=msg.get("threadId"),
            account_email=self.account_email,
            sender_name=sender_name or None,
            sender_email=sender_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            attachments=attachments,
        )


def cli_authorize() -> None:
    """One-time OAuth: writes a refresh token to disk."""
    s = load_settings()
    creds = _load_creds(s.gmail_client_secret_file, s.gmail_token_file)
    log.info("gmail.authorized", token_file=str(s.gmail_token_file), email=s.gmail_user_email)
    assert creds.valid
