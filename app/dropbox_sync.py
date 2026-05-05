"""Pull the source-of-truth .xlsx from Dropbox and apply it.

Dropbox's API is small enough here that we hit it directly with httpx instead of
pulling in the full `dropbox` SDK. We need exactly two endpoints:

- POST https://api.dropbox.com/oauth2/token  (refresh-token → short-lived access token)
- POST https://content.dropboxapi.com/2/files/download  (download the file by path)

`try_pull()` is the friendly entrypoint: it never raises, and returns a dict
with `configured`, `ok`, and either count fields or an `error` string. Callers
treat a failed pull as "use last-known DB data and warn the owner".
"""
import json

import httpx

from . import config, sheet_import

TOKEN_URL = "https://api.dropbox.com/oauth2/token"
DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"


def is_configured() -> bool:
    return bool(
        config.DROPBOX_APP_KEY
        and config.DROPBOX_APP_SECRET
        and config.DROPBOX_REFRESH_TOKEN
        and config.DROPBOX_FILE_PATH
    )


def _get_access_token() -> str:
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": config.DROPBOX_REFRESH_TOKEN,
        },
        auth=(config.DROPBOX_APP_KEY, config.DROPBOX_APP_SECRET),
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"token refresh failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


def _download(token: str, path: str) -> bytes:
    r = httpx.post(
        DOWNLOAD_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": path}),
        },
        timeout=30,
    )
    if r.status_code != 200:
        # Dropbox returns errors as JSON in the body for 4xx/5xx
        raise RuntimeError(f"download failed ({r.status_code}): {r.text[:200]}")
    return r.content


def try_pull() -> dict:
    """Pull, parse, apply. Returns a status dict; never raises."""
    if not is_configured():
        return {"configured": False}
    try:
        token = _get_access_token()
        data = _download(token, config.DROPBOX_FILE_PATH)
        records = sheet_import.parse_workbook(data)
        counts = sheet_import.apply_records(records)
        return {"configured": True, "ok": True, **counts}
    except Exception as e:
        return {"configured": True, "ok": False, "error": str(e)}
