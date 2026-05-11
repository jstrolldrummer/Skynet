from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from bid_watcher.models import BidClassification, IncomingEmail
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You triage incoming emails for Wyatt + Gray Custom Homes, a \
high-end residential general contractor in Connecticut. Your job: decide if an \
email is a BID REQUEST — i.e., the sender is inviting Wyatt + Gray to propose \
pricing for construction work.

POSITIVE SIGNALS (treat as bid request, confidence >= 0.8 if multiple present):
- An architect, designer, or homeowner attaches drawings, plans, CDs, or a
  pricing set and asks for an estimate, pricing, or a budget range.
- Phrases like: "invite you to provide a preliminary pricing estimate",
  "start pricing this", "preparing your estimate", "scope of work attached",
  "for bid", "for budget", "ITB", "request for proposal", "RFP".
- An architect or designer (firm name like "Interiors", "Architects", "Design"
  in their domain) sends a PDF labeled "CDs", "Pricing Set", "Project Overview",
  "Specifications", "Scope".
- Mention of a project address (street + town/state) and a residential trade
  (kitchen, bath, roof, addition, renovation, etc.).

NEGATIVE SIGNALS (treat as NOT a bid request):
- Replies on an existing W+G project (look for thread context).
- Marketing, vendor outreach, sales pitches.
- Personal correspondence, scheduling, change-order discussions on active jobs.
- Permit applications, invoices, lien waivers, AIA pay apps coming back.

When it IS a bid request, extract whatever you can. If client_company is unclear
but the sender is an architect/designer forwarding for an end client, use the
end client's name as `client_company` and put the firm as `contact_name`'s
employer in `notes`. Project name should be terse and folder-safe (e.g.
"Gorodnitsky Kid's Bath", "80 Cross Ridge Road"). Use null for unknowns. Never
invent details not present in the email.

Likely trades (use only what's actually implied): General, Demo, Framing,
Roofing, Siding, Windows, Doors, Insulation, Drywall, Plumbing, Electrical,
HVAC, Tile, Flooring, Painting, Cabinetry, Millwork, Masonry, Stone Veneer,
Gutters, Site / Excavation, Landscape.

Output ONLY a JSON object with this exact shape:
{
  "is_bid_request": boolean,
  "confidence": number,            // 0..1
  "client_company": string|null,
  "contact_name": string|null,
  "project_name": string|null,
  "project_location": string|null,
  "due_date": string|null,         // ISO YYYY-MM-DD or null
  "scope_summary": string,         // empty string if not a bid; otherwise 2-5 sentences
  "trades": string[],              // [] if not a bid or unknown
  "notes": string|null             // brief reasoning or caveat
}

EXAMPLE 1 (architect inviting bid):
Email from "Kenneth Secco <Ken@hk2arch.com>", subject "80 Cross Ridge Road",
body "Howard and I are reaching out to invite you to provide a preliminary
pricing estimate for an interior renovation project on behalf of the owners,
Alex and Lisa Olsen... we would appreciate receiving your estimate by the end
of the day on May 20th.", attachments include "Project Overview.pdf" and
"Olsen Pricing Set.pdf".
->
{"is_bid_request": true, "confidence": 0.97, "client_company":
"Alex and Lisa Olsen", "contact_name": "Kenneth Secco",
"project_name": "80 Cross Ridge Road", "project_location": "New Canaan, CT",
"due_date": "<current-year>-05-20", "scope_summary":
"Interior renovation of a Blue Home prefab in New Canaan, CT. Includes finishing
the basement and modifying the ground floor plan for the Olsen family. Some
exterior scope: window replacement, a skylight, and an egress well. Drawings
are schematic; budget range with allowances is acceptable.",
"trades": ["General","Demo","Framing","Drywall","Windows","Painting"],
"notes": "Sender is HK2 Architecture; end client is the Olsens."}

EXAMPLE 2 (designer forwarding plans):
Email from "Tori McBrien <tori@mcbrieninteriors.com>", subject
"Gorodnitsky Kid's Bath, Darien, CT", body "I wanted to get these over to you
so we can start pricing this... should give you an idea of the scope of work",
attachment "YRG Bath Prelim CDs 5.11.26.pdf".
->
{"is_bid_request": true, "confidence": 0.94, "client_company": "Gorodnitsky",
"contact_name": "Tori McBrien", "project_name": "Gorodnitsky Kid's Bath",
"project_location": "Darien, CT", "due_date": null, "scope_summary":
"Kid's bathroom renovation at the Gorodnitsky residence in Darien, CT.
Preliminary CDs attached; schedules and additional details to follow. Returning
client — prior positive relationship.", "trades":
["Demo","Plumbing","Tile","Carpentry","Painting","Electrical"],
"notes": "McBrien Interiors is the designer; Gorodnitsky is the homeowner."}
"""


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
