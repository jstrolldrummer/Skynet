import secrets
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from twilio.request_validator import RequestValidator

from . import config, db, dropbox_sync, messaging, sheet_import
from .auth import require_admin

app = FastAPI(title="Subtext — Subcontractor Follow-ups")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/admin")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, _user: str = Depends(require_admin)):
    with db.connect() as conn:
        subs = conn.execute(
            "SELECT * FROM subcontractors ORDER BY active DESC, name"
        ).fetchall()
        jobs = conn.execute(
            """
            SELECT jobs.*, subcontractors.name AS sub_name
            FROM jobs
            JOIN subcontractors ON subcontractors.id = jobs.subcontractor_id
            ORDER BY jobs.status, jobs.created_at DESC
            """
        ).fetchall()
        items = conn.execute(
            """
            SELECT open_items.*, jobs.title AS job_title, subcontractors.name AS sub_name
            FROM open_items
            JOIN jobs ON jobs.id = open_items.job_id
            JOIN subcontractors ON subcontractors.id = jobs.subcontractor_id
            ORDER BY open_items.status, open_items.created_at DESC
            """
        ).fetchall()
        recent_messages = conn.execute(
            """
            SELECT messages.*, subcontractors.name AS sub_name
            FROM messages
            LEFT JOIN subcontractors ON subcontractors.id = messages.subcontractor_id
            ORDER BY sent_at DESC
            LIMIT 100
            """
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "subs": subs,
            "jobs": jobs,
            "items": items,
            "messages": recent_messages,
            "company": config.COMPANY_NAME,
            "flash": request.query_params.get("msg"),
            "flash_kind": request.query_params.get("kind", "info"),
            "dropbox_configured": dropbox_sync.is_configured(),
            "dropbox_path": config.DROPBOX_FILE_PATH,
        },
    )


@app.post("/admin/refresh-from-dropbox")
def refresh_from_dropbox(_user: str = Depends(require_admin)):
    result = dropbox_sync.try_pull()
    if not result.get("configured"):
        msg = "Dropbox isn't configured. Set DROPBOX_* env vars first."
        kind = "error"
    elif not result.get("ok"):
        msg = f"Dropbox pull failed: {result.get('error', 'unknown error')}"
        kind = "error"
    else:
        msg = (
            f"Pulled from Dropbox: {result['items']} open items across "
            f"{result['jobs']} jobs. Subs: {result['subs_added']} new, "
            f"{result['subs_updated']} updated."
        )
        kind = "ok"
    return RedirectResponse(f"/admin?kind={kind}&msg={quote_plus(msg)}", status_code=303)


@app.post("/admin/upload-sheet")
async def upload_sheet(
    file: UploadFile = File(...),
    _user: str = Depends(require_admin),
):
    data = await file.read()
    try:
        records = sheet_import.parse_workbook(data)
        counts = sheet_import.apply_records(records)
    except sheet_import.SheetError as e:
        return RedirectResponse(
            f"/admin?kind=error&msg={quote_plus(str(e))}", status_code=303
        )
    msg = (
        f"Loaded {counts['items']} open items across {counts['jobs']} jobs. "
        f"Subs: {counts['subs_added']} new, {counts['subs_updated']} updated."
    )
    return RedirectResponse(f"/admin?kind=ok&msg={quote_plus(msg)}", status_code=303)


@app.get("/admin/sheet-template")
def sheet_template(_user: str = Depends(require_admin)):
    data = sheet_import.template_workbook_bytes()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="subtext-template.xlsx"'},
    )


@app.post("/admin/subs/{sub_id}/toggle")
def toggle_sub(sub_id: int, _user: str = Depends(require_admin)):
    with db.connect() as conn:
        conn.execute(
            "UPDATE subcontractors SET active = 1 - active WHERE id = ?", (sub_id,)
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/jobs/{job_id}/status")
def update_job_status(
    job_id: int,
    status_value: str = Form(...),
    _user: str = Depends(require_admin),
):
    with db.connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status_value, job_id))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/items/{item_id}/status")
def update_item_status(
    item_id: int,
    status_value: str = Form(...),
    _user: str = Depends(require_admin),
):
    with db.connect() as conn:
        conn.execute(
            "UPDATE open_items SET status = ? WHERE id = ?", (status_value, item_id)
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/send-now")
def admin_send_now(_user: str = Depends(require_admin)):
    return messaging.send_daily_followups()


def _check_task_token(token: str) -> None:
    if not secrets.compare_digest(token or "", config.TASK_TOKEN or ""):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/tasks/send-followups")
def cron_send_followups(x_task_token: str = Header(default="")):
    """Immediate one-shot sweep — bypasses the preview/pending flow."""
    _check_task_token(x_task_token)
    return messaging.send_daily_followups()


@app.post("/tasks/preview-followups")
def cron_preview_followups(x_task_token: str = Header(default="")):
    """Build today's pending list and text the owner a preview."""
    _check_task_token(x_task_token)
    return messaging.prepare_preview()


@app.post("/tasks/send-pending")
def cron_send_pending(x_task_token: str = Header(default="")):
    """Send everything currently pending (the 8am cron)."""
    _check_task_token(x_task_token)
    return messaging.send_pending()


def _twilio_signature_ok(request: Request, form: dict) -> bool:
    """Verify the X-Twilio-Signature header against the configured auth token.

    Skipped (returns True) when TWILIO_AUTH_TOKEN or PUBLIC_URL aren't set —
    that's the local-dev case. In production both should be set.
    """
    if not config.TWILIO_AUTH_TOKEN or not config.PUBLIC_URL:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    url = config.PUBLIC_URL.rstrip("/") + request.url.path
    if request.url.query:
        url = f"{url}?{request.url.query}"
    validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
    return validator.validate(url, dict(form), signature)


@app.post("/sms/incoming")
async def sms_incoming(request: Request):
    form = await request.form()
    if not _twilio_signature_ok(request, form):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    from_number = form.get("From", "")
    body = form.get("Body", "")

    if config.OWNER_PHONE and from_number == config.OWNER_PHONE:
        reply = messaging.handle_owner_command(body)
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO messages (subcontractor_id, direction, body) VALUES (NULL, 'owner-in', ?)",
                (body,),
            )
            if reply:
                conn.execute(
                    "INSERT INTO messages (subcontractor_id, direction, body) VALUES (NULL, 'owner-out', ?)",
                    (reply,),
                )
        if reply:
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f"<Response><Message>{_xml_escape(reply)}</Message></Response>"
            )
            return Response(content=twiml, media_type="application/xml")

    with db.connect() as conn:
        sub = conn.execute(
            "SELECT id FROM subcontractors WHERE phone = ?", (from_number,)
        ).fetchone()
        sub_id = sub["id"] if sub else None
        conn.execute(
            "INSERT INTO messages (subcontractor_id, direction, body) VALUES (?, 'inbound', ?)",
            (sub_id, body),
        )
    twiml = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
    return Response(content=twiml, media_type="application/xml")


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
