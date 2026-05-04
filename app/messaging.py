from . import config, db, sms


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


def send_daily_followups() -> dict:
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
            try:
                sid = sms.send_sms(sub["phone"], body)
            except Exception as e:
                errors.append(f"{sub['name']}: {e}")
                continue
            conn.execute(
                "INSERT INTO messages (subcontractor_id, direction, body, twilio_sid)"
                " VALUES (?, 'outbound', ?, ?)",
                (sub["id"], body, sid),
            )
            sent += 1
    return {"sent": sent, "skipped": skipped, "errors": errors}
