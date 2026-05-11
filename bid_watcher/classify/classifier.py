from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from bid_watcher.models import BidClassification, IncomingEmail
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You triage incoming emails for Wyatt & Gray, a construction \
contractor. Your job: decide if an email is a BID REQUEST — i.e., the sender \
is inviting Wyatt & Gray to propose pricing for work, sharing a scope of work, \
plans/drawings, or an invitation to bid. Forwarded scopes from a colleague \
also count. Marketing, replies on existing projects, ordinary correspondence, \
and personal mail are NOT bid requests.

When it IS a bid request, extract whatever you can: client/company, contact \
name, project name, project location, due date (ISO YYYY-MM-DD if explicit), \
scope summary (2-5 sentences), and likely trade tags. Use null for unknowns. \
Never invent details that are not in the email.

Output ONLY a JSON object with this exact shape:
{
  "is_bid_request": boolean,
  "confidence": number,            // 0..1
  "client_company": string|null,
  "contact_name": string|null,
  "project_name": string|null,
  "project_location": string|null,
  "due_date": string|null,         // ISO YYYY-MM-DD or null
  "scope_summary": string,         // empty string if not a bid
  "trades": string[],              // [] if not a bid or unknown
  "notes": string|null             // brief reasoning or caveat
}"""


def _build_user_message(email: IncomingEmail) -> str:
    att_list = "\n".join(f"- {a.filename} ({a.mime_type}, {len(a.content)} bytes)" for a in email.attachments) or "(none)"
    return (
        f"From: {email.sender_name or ''} <{email.sender_email}>\n"
        f"To: {email.account_email}\n"
        f"Subject: {email.subject}\n"
        f"Received: {email.received_at.isoformat()}\n"
        f"Attachments:\n{att_list}\n"
        f"\n--- Body ---\n{email.body_text[:12000]}"
    )


class Classifier:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10), reraise=True)
    def classify(self, email: IncomingEmail) -> BidClassification:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(email)}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        data = _extract_json(text)
        return BidClassification(
            is_bid_request=bool(data.get("is_bid_request", False)),
            confidence=float(data.get("confidence", 0.0)),
            client_company=data.get("client_company") or None,
            contact_name=data.get("contact_name") or None,
            project_name=data.get("project_name") or None,
            project_location=data.get("project_location") or None,
            due_date=data.get("due_date") or None,
            scope_summary=data.get("scope_summary") or "",
            trades=list(data.get("trades") or []),
            notes=data.get("notes") or None,
        )


def _extract_json(text: str) -> dict[str, Any]:
    # Tolerate models wrapping JSON in fenced blocks or chatter
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in classifier response: {text[:200]}")
    return json.loads(text[start : end + 1])
