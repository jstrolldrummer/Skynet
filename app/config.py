import os

from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
TASK_TOKEN = os.environ.get("TASK_TOKEN", "change-me")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./skynet.db")

COMPANY_NAME = os.environ.get("COMPANY_NAME", "Wyatt & Gray Custom Homes")
SENDER_NAME = os.environ.get("SENDER_NAME", "Joe")

# Your personal phone in E.164 (e.g. +15125551234). Receives the morning preview
# and can reply with commands like "skip 1", "send", "status".
OWNER_PHONE = os.environ.get("OWNER_PHONE", "")

# Public URL of the deployed app (e.g. https://skynet-xxxx.onrender.com). Used to
# verify Twilio webhook signatures. Falls back to Render's auto-injected value.
PUBLIC_URL = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")

# Local timezone for "is it a weekend?" and similar wall-clock checks.
TIMEZONE = os.environ.get("TIMEZONE", "America/Chicago")

# When true, the 7:30am preview and immediate-send sweeps are no-ops on Sat/Sun.
SKIP_WEEKENDS = os.environ.get("SKIP_WEEKENDS", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Dropbox sync. When all four are set, the app pulls the .xlsx automatically at
# preview/send time and on demand from the admin UI. See README + the
# `python -m app.dropbox_setup` helper for getting a refresh token.
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN", "")
DROPBOX_FILE_PATH = os.environ.get("DROPBOX_FILE_PATH", "/subtext.xlsx")
