"""Parse and apply an uploaded .xlsx of subs/jobs/open items.

Sheet format (first row is headers, case/spacing tolerant):

    Name              | Phone           | Job              | Item
    Carlos Garcia     | 512-555-1234    | 123 Oak St       | finish drywall
    Carlos Garcia     | 512-555-1234    | 123 Oak St       | punchlist photos
    Jim Smith         | 512-555-9876    | 47 Pine Ln       | rough plumbing

Each row = one open item. A sub is identified by phone; a job is identified by
(sub, job title). On apply we:

- preserve subcontractors (upsert by phone) and the messages history
- wipe existing jobs + open_items and rebuild them from the sheet

So each upload is "this is the truth right now" — no merging surprises.
"""
from io import BytesIO

from openpyxl import Workbook, load_workbook

from . import db
from .messaging import normalize_phone

EXPECTED = ("name", "phone", "job", "item")


class SheetError(ValueError):
    pass


def _header_index(headers: list[str]) -> dict[str, int]:
    """Map each expected key to a column index, tolerating variants like
    'phone number' or 'job title'."""
    found: dict[str, int] = {}
    normalized = [(h or "").strip().lower() for h in headers]
    for key in EXPECTED:
        for i, h in enumerate(normalized):
            if h == key or h.startswith(key + " ") or h.endswith(" " + key):
                found[key] = i
                break
        if key not in found:
            raise SheetError(
                f"Missing column '{key}'. First row must contain: "
                f"{', '.join(EXPECTED).title()}. Got: {headers}"
            )
    return found


def parse_workbook(data: bytes) -> list[dict]:
    try:
        wb = load_workbook(filename=BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise SheetError(f"Could not open spreadsheet: {e}") from e
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SheetError("Spreadsheet is empty.")
    idx = _header_index(list(rows[0]))

    out: list[dict] = []
    for r in rows[1:]:
        if r is None:
            continue
        cells = [("" if c is None else str(c).strip()) for c in r]
        # pad short rows
        while len(cells) < max(idx.values()) + 1:
            cells.append("")
        if not any(cells):
            continue
        record = {k: cells[idx[k]] for k in EXPECTED}
        # Skip rows missing required values rather than failing the whole upload.
        if not record["name"] or not record["phone"]:
            continue
        if not record["job"] or not record["item"]:
            continue
        out.append(record)
    if not out:
        raise SheetError("No usable rows found. Every row needs Name, Phone, Job, and Item.")
    return out


def apply_records(records: list[dict]) -> dict:
    """Replace jobs + open items from the sheet. Subs upserted by phone."""
    counts = {"subs_added": 0, "subs_updated": 0, "jobs": 0, "items": 0}
    with db.connect() as conn:
        # Wipe existing jobs (cascade deletes open_items via FK ON DELETE CASCADE)
        conn.execute("DELETE FROM open_items")
        conn.execute("DELETE FROM jobs")

        sub_id_by_phone: dict[str, int] = {}
        for rec in records:
            phone = normalize_phone(rec["phone"])
            if phone in sub_id_by_phone:
                continue
            existing = conn.execute(
                "SELECT id FROM subcontractors WHERE phone = ?", (phone,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE subcontractors SET name = ?, active = 1 WHERE id = ?",
                    (rec["name"], existing["id"]),
                )
                sub_id_by_phone[phone] = existing["id"]
                counts["subs_updated"] += 1
            else:
                cur = conn.execute(
                    "INSERT INTO subcontractors (name, phone) VALUES (?, ?)",
                    (rec["name"], phone),
                )
                sub_id_by_phone[phone] = cur.lastrowid
                counts["subs_added"] += 1

        job_id_by_key: dict[tuple[int, str], int] = {}
        for rec in records:
            phone = normalize_phone(rec["phone"])
            sub_id = sub_id_by_phone[phone]
            key = (sub_id, rec["job"])
            if key not in job_id_by_key:
                cur = conn.execute(
                    "INSERT INTO jobs (title, subcontractor_id) VALUES (?, ?)",
                    (rec["job"], sub_id),
                )
                job_id_by_key[key] = cur.lastrowid
                counts["jobs"] += 1
            conn.execute(
                "INSERT INTO open_items (job_id, description) VALUES (?, ?)",
                (job_id_by_key[key], rec["item"]),
            )
            counts["items"] += 1
    return counts


def template_workbook_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Open items"
    ws.append(["Name", "Phone", "Job", "Item"])
    examples = [
        ("Carlos Garcia", "512-555-1234", "123 Oak St", "finish drywall in master"),
        ("Carlos Garcia", "512-555-1234", "123 Oak St", "punchlist photos to me"),
        ("Carlos Garcia", "512-555-1234", "47 Pine Ln", "confirm Tuesday start"),
        ("Jim Smith", "512-555-9876", "47 Pine Ln", "rough plumbing inspection"),
    ]
    for row in examples:
        ws.append(row)
    for col, width in zip("ABCD", (20, 16, 28, 40)):
        ws.column_dimensions[col].width = width
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
