import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import config, db, messaging
from .auth import require_admin

app = FastAPI(title="Skynet — Subcontractor Follow-ups")
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
        },
    )


@app.post("/admin/subs")
def add_sub(
    name: str = Form(...),
    phone: str = Form(...),
    _user: str = Depends(require_admin),
):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO subcontractors (name, phone) VALUES (?, ?)",
            (name.strip(), messaging.normalize_phone(phone)),
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/subs/{sub_id}/toggle")
def toggle_sub(sub_id: int, _user: str = Depends(require_admin)):
    with db.connect() as conn:
        conn.execute(
            "UPDATE subcontractors SET active = 1 - active WHERE id = ?", (sub_id,)
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/jobs")
def add_job(
    title: str = Form(...),
    subcontractor_id: int = Form(...),
    _user: str = Depends(require_admin),
):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (title, subcontractor_id) VALUES (?, ?)",
            (title.strip(), subcontractor_id),
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


@app.post("/admin/items")
def add_item(
    job_id: int = Form(...),
    description: str = Form(...),
    _user: str = Depends(require_admin),
):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO open_items (job_id, description) VALUES (?, ?)",
            (job_id, description.strip()),
        )
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


@app.post("/sms/incoming")
async def sms_incoming(request: Request):
    form = await request.form()
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
