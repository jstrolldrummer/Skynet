from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import msal
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from bid_watcher.config import load_settings
from bid_watcher.models import Attachment, IncomingEmail
from bid_watcher.sources import EmailSource
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read"]


def _build_app(tenant_id: str, client_id: str, cache_file: Path) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
    cache = msal.SerializableTokenCache()
    if cache_file.exists():
        cache.deserialize(cache_file.read_text())
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app, cache


def _persist(cache: msal.SerializableTokenCache, cache_file: Path) -> None:
    if cache.has_state_changed:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(cache.serialize())


def _acquire_token(app: msal.PublicClientApplication) -> str:
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")
    print(flow["message"], flush=True)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Device flow failed: {result}")
    return result["access_token"]


class OutlookSource(EmailSource):
    name = "outlook"

    def __init__(self, tenant_id: str, client_id: str, cache_file: Path, account_email: str) -> None:
        self.account_email = account_email
        self._app, self._cache = _build_app(tenant_id, client_id, cache_file)
        self._cache_file = cache_file

    def _token(self) -> str:
        token = _acquire_token(self._app)
        _persist(self._cache, self._cache_file)
        return token

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16), reraise=True)
    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token()}", "Prefer": "outlook.body-content-type=\"text\""}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_since(self, since: datetime) -> Iterable[IncomingEmail]:
        iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "$filter": f"receivedDateTime gt {iso} and hasAttachments eq true",
            "$orderby": "receivedDateTime asc",
            "$top": 50,
            "$select": "id,conversationId,subject,from,receivedDateTime,bodyPreview,body,hasAttachments",
        }
        url = f"{GRAPH}/me/messages"
        while url:
            data = self._get(url, params=params)
            params = None
            for msg in data.get("value", []):
                yield self._convert(msg)
            url = data.get("@odata.nextLink") or ""

    def _convert(self, msg: dict) -> IncomingEmail:
        from_obj = (msg.get("from") or {}).get("emailAddress") or {}
        received = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
        body = (msg.get("body") or {}).get("content") or msg.get("bodyPreview") or ""
        atts: list[Attachment] = []
        if msg.get("hasAttachments"):
            atts_data = self._get(f"{GRAPH}/me/messages/{msg['id']}/attachments")
            for a in atts_data.get("value", []):
                if a.get("@odata.type") != "#microsoft.graph.fileAttachment":
                    continue
                import base64
                content = base64.b64decode(a.get("contentBytes") or "")
                atts.append(
                    Attachment(
                        filename=a.get("name") or "attachment",
                        mime_type=a.get("contentType") or "application/octet-stream",
                        content=content,
                    )
                )
        return IncomingEmail(
            source="outlook",
            message_id=msg["id"],
            thread_id=msg.get("conversationId"),
            account_email=self.account_email,
            sender_name=from_obj.get("name"),
            sender_email=from_obj.get("address", ""),
            subject=msg.get("subject", ""),
            body_text=body,
            body_html=None,
            received_at=received,
            attachments=atts,
        )


def cli_authorize() -> None:
    s = load_settings()
    if not s.outlook_client_id:
        raise SystemExit("OUTLOOK_CLIENT_ID must be set in .env first")
    src = OutlookSource(s.outlook_tenant_id, s.outlook_client_id, s.outlook_token_cache_file, s.outlook_user_email or "")
    _ = src._token()
    log.info("outlook.authorized", cache_file=str(s.outlook_token_cache_file), email=s.outlook_user_email)
