import re
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import config, db, dropbox_sync, sms


def _format_dropbox_warning(result: dict) -> str | None:
    """Return a short human-readable warning if the Dropbox pull failed, else None."""
    if not result.get("configured"):
        return None
    if result.get("ok"):
        return None
    err = (result.get("error") or "").strip()
    if len(err) > 100:
        err = err[:97] + "..."
    return f"Dropbox pull failed: {err}. Using last-known data."


def _is_weekend_locally() -> bool:
    try:
        tz = ZoneInfo(config.TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).weekday() >= 5


def normalize_phone(raw: str) -> str:
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    if cleaned.startswith("+"):
        return cleaned
    if len(cleaned) == 10:
        return "+1" + cleaned
    if len(cleaned) == 11 and cleaned.startswith("1"):
        return "+" + cleaned
    return cleaned


def first_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[0] if parts else ""


def fetch_open_items_for_sub(conn, sub_id: int):
    return conn.execute(
        """
        SELECT open_items.id, open_items.description, jobs.title AS job_title
        FROM open_items
        JOIN jobs ON jobs.id = open_items.job_id
        WHERE open_items.status = 'open'
          AND jobs.status = 'active'
          AND jobs.subcontractor_id = ?
        ORDER BY jobs.title, open_items.id
        """,
        (sub_id,),
    ).fetchall()


def compose_message(sub_name: str, items) -> str:
    lines = [
        f"Morning {first_name(sub_name)} — {config.SENDER_NAME} with {config.COMPANY_NAME}. Your open items:"
    ]
    for i, item in enumerate(items, start=1):
        lines.append(f"{i}. {item['job_title']} — {item['description']}")
    lines.append("")
    lines.append('Reply with a quick status on each (e.g. "1 done, 2 by Friday"). Reply STOP to opt out.')
    return "\n".join(lines)


def _send_one(conn, sub_id: int, phone: str, body: str) -> str | None:
    """Send a single SMS, log it to messages, return Twilio SID or None on error."""
    try:
        sid = sms.send_sms(phone, body)
    except Exception as e:
        conn.execute(
            "INSERT INTO messages (subcontractor_id, direction, body) VALUES (?, 'error', ?)",
            (sub_id, f"[send failed] {e}\n\n{body}"),
        )
        return None
    conn.execute(
        "INSERT INTO messages (subcontractor_id, direction, body, twilio_sid)"
        " VALUES (?, 'outbound', ?, ?)",
        (sub_id, body, sid),
    )
    return sid


def send_daily_followups() -> dict:
    """Immediate sweep: compose and send every active sub's open items right now."""
    if config.SKIP_WEEKENDS and _is_weekend_locally():
        return {"skipped": "weekend", "sent": 0}
    dropbox_result = dropbox_sync.try_pull()
    sent = 0
    skipped = 0
    errors = []
    with db.connect() as conn:
        subs = conn.execute(
            "SELECT id, name, phone FROM subcontractors WHERE active = 1"
        ).fetchall()
        for sub in subs:
            items = fetch_open_items_for_sub(conn, sub["id"])
            if not items:
                skipped += 1
                continue
            body = compose_message(sub["name"], items)
            sid = _send_one(conn, sub["id"], sub["phone"], body)
            if sid:
                sent += 1
            else:
                errors.append(sub["name"])
    return {
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "dropbox": dropbox_result,
    }


def prepare_preview() -> dict:
    """Build pending_sends rows for today and text the owner a preview.

    Clears any leftover pending rows first so each morning starts clean.
    """
    if not config.OWNER_PHONE:
        return {"error": "OWNER_PHONE not configured"}
    if config.SKIP_WEEKENDS and _is_weekend_locally():
        return {"skipped": "weekend", "queued": 0, "preview_sent": False}

    dropbox_result = dropbox_sync.try_pull()
    dropbox_warning = _format_dropbox_warning(dropbox_result)

    queued = []
    with db.connect() as conn:
        # Clear any unsent leftovers from previous runs.
        conn.execute("DELETE FROM pending_sends WHERE status = 'pending'")

        subs = conn.execute(
            "SELECT id, name, phone FROM subcontractors WHERE active = 1 ORDER BY name"
        ).fetchall()
        seq = 0
        for sub in subs:
            items = fetch_open_items_for_sub(conn, sub["id"])
            if not items:
                continue
            seq += 1
            body = compose_message(sub["name"], items)
            conn.execute(
                "INSERT INTO pending_sends (subcontractor_id, body, sequence_number)"
                " VALUES (?, ?, ?)",
                (sub["id"], body, seq),
            )
            queued.append({"seq": seq, "name": sub["name"], "item_count": len(items)})

        if not queued:
            # Still tell the owner if Dropbox blew up but there happens to be no work.
            if dropbox_warning:
                try:
                    sms.send_sms(config.OWNER_PHONE, f"Subtext: {dropbox_warning}")
                except Exception:
                    pass
            return {
                "queued": 0,
                "preview_sent": False,
                "dropbox": dropbox_result,
            }

        preview_body = _format_preview(queued, dropbox_warning)
        try:
            sms.send_sms(config.OWNER_PHONE, preview_body)
            preview_sent = True
        except Exception as e:
            preview_sent = False
            queued.append({"preview_error": str(e)})

    return {
        "queued": len(queued),
        "preview_sent": preview_sent,
        "subs": queued,
        "dropbox": dropbox_result,
    }


def _format_preview(queued: list, warning: str | None = None) -> str:
    lines = []
    if warning:
        lines.append(f"⚠ {warning}")
        lines.append("")
    lines.append(f"Subtext: {len(queued)} follow-up{'s' if len(queued) != 1 else ''} queued for 8am.")
    for q in queued:
        lines.append(f"{q['seq']}. {q['name']} ({q['item_count']} item{'s' if q['item_count'] != 1 else ''})")
    lines.append("")
    lines.append('Reply "skip 1" or "skip 1,3" to drop, "send" to fire now, "status" to recheck.')
    return "\n".join(lines)


def send_pending() -> dict:
    """Send everything currently pending. Called by the 8am cron, or by 'send' command."""
    sent = 0
    errors = []
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT pending_sends.id, pending_sends.body, pending_sends.subcontractor_id,
                   subcontractors.phone, subcontractors.name
            FROM pending_sends
            JOIN subcontractors ON subcontractors.id = pending_sends.subcontractor_id
            WHERE pending_sends.status = 'pending'
            ORDER BY pending_sends.sequence_number
            """
        ).fetchall()
        for row in rows:
            sid = _send_one(conn, row["subcontractor_id"], row["phone"], row["body"])
            if sid:
                conn.execute(
                    "UPDATE pending_sends SET status = 'sent', sent_at = CURRENT_TIMESTAMP, twilio_sid = ? WHERE id = ?",
                    (sid, row["id"]),
                )
                sent += 1
            else:
                errors.append(row["name"])
    return {"sent": sent, "errors": errors}


# ---- Owner command parsing ----

_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
_NUM_RE = re.compile(r"\d+")


def _parse_skip_targets(text: str) -> list[int]:
    """Extract sequence numbers from "skip 1", "skip 1,3", "skip 1-3", etc."""
    targets: set[int] = set()
    for m in _RANGE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            targets.update(range(a, b + 1))
    text_no_ranges = _RANGE_RE.sub(" ", text)
    for m in _NUM_RE.finditer(text_no_ranges):
        targets.add(int(m.group(0)))
    return sorted(targets)


def handle_owner_command(body: str) -> str | None:
    """Process a text from OWNER_PHONE. Returns a reply string, or None if not a command."""
    text = body.strip().lower()
    if not text:
        return None

    if text.startswith("skip"):
        targets = _parse_skip_targets(text[4:])
        if not targets:
            return "Skip what? Try 'skip 1' or 'skip 1,3'."
        with db.connect() as conn:
            placeholders = ",".join("?" * len(targets))
            cur = conn.execute(
                f"UPDATE pending_sends SET status = 'skipped'"
                f" WHERE status = 'pending' AND sequence_number IN ({placeholders})",
                targets,
            )
            skipped = cur.rowcount
            remaining = conn.execute(
                "SELECT sequence_number, subcontractors.name FROM pending_sends"
                " JOIN subcontractors ON subcontractors.id = pending_sends.subcontractor_id"
                " WHERE status = 'pending' ORDER BY sequence_number"
            ).fetchall()
        if not remaining:
            return f"Skipped {skipped}. Nothing left to send."
        rest = ", ".join(f"{r['sequence_number']}.{first_name(r['name'])}" for r in remaining)
        return f"Skipped {skipped}. Still queued: {rest}."

    if text in ("send", "send now", "fire", "go"):
        result = send_pending()
        return f"Sent {result['sent']}." + (f" Errors: {', '.join(result['errors'])}." if result["errors"] else "")

    if text in ("status", "queue", "list"):
        with db.connect() as conn:
            remaining = conn.execute(
                "SELECT sequence_number, subcontractors.name FROM pending_sends"
                " JOIN subcontractors ON subcontractors.id = pending_sends.subcontractor_id"
                " WHERE status = 'pending' ORDER BY sequence_number"
            ).fetchall()
        if not remaining:
            return "Nothing queued."
        rest = ", ".join(f"{r['sequence_number']}.{first_name(r['name'])}" for r in remaining)
        return f"Queued: {rest}."

    return None
