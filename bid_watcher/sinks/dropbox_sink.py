from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import FolderMetadata, WriteMode
from tenacity import retry, stop_after_attempt, wait_exponential

from bid_watcher.config import load_settings
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)

_INVALID_PATH = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def sanitize_segment(name: str, max_len: int = 80) -> str:
    cleaned = _INVALID_PATH.sub(" ", name).strip().rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:max_len] or "Unknown").rstrip()


def build_project_folder_name(client_company: Optional[str], project_name: Optional[str], received_at_iso: str) -> str:
    client = sanitize_segment(client_company or "Unknown Client")
    project = sanitize_segment(project_name or f"Bid {received_at_iso[:10]}")
    return f"{client} - {project}"


class DropboxSink:
    SUBFOLDERS = ("Drawings", "Scope", "Correspondence", "Proposal")
    # Map common drawing/scope extensions to their landing subfolder
    DRAWING_EXTS = {".pdf", ".dwg", ".dxf", ".rvt", ".ifc", ".skp", ".vwx"}
    SCOPE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".rtf"}

    def __init__(self, app_key: str, app_secret: str, refresh_token: str, estimating_root: str) -> None:
        self._dbx = dropbox.Dropbox(
            app_key=app_key,
            app_secret=app_secret,
            oauth2_refresh_token=refresh_token,
        )
        self.estimating_root = estimating_root.rstrip("/")

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16), reraise=True)
    def ensure_folder(self, path: str) -> None:
        try:
            self._dbx.files_create_folder_v2(path)
        except ApiError as e:
            # If it already exists, that's fine
            if "conflict/folder" in str(e):
                return
            raise

    def create_project_skeleton(self, folder_name: str) -> str:
        project_path = f"{self.estimating_root}/{folder_name}"
        self.ensure_folder(project_path)
        for sub in self.SUBFOLDERS:
            self.ensure_folder(f"{project_path}/{sub}")
        log.info("dropbox.skeleton_created", path=project_path)
        return project_path

    def classify_attachment(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext in self.DRAWING_EXTS:
            return "Drawings"
        if ext in self.SCOPE_EXTS:
            return "Scope"
        return "Scope"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16), reraise=True)
    def upload_bytes(self, dest_path: str, content: bytes) -> None:
        self._dbx.files_upload(content, dest_path, mode=WriteMode.add, autorename=True)
        log.info("dropbox.uploaded", path=dest_path, size=len(content))


def cli_authorize() -> None:
    """Walks through Dropbox OAuth2 PKCE to mint a refresh token. Prints it; user pastes into .env."""
    s = load_settings()
    if not s.dropbox_app_key:
        raise SystemExit("DROPBOX_APP_KEY must be set in .env first")
    flow = dropbox.DropboxOAuth2FlowNoRedirect(
        consumer_key=s.dropbox_app_key,
        consumer_secret=s.dropbox_app_secret,
        token_access_type="offline",
    )
    auth_url = flow.start()
    print("1. Open this URL in a browser and approve:\n   " + auth_url)
    code = input("2. Paste the auth code here: ").strip()
    result = flow.finish(code)
    print("\nDROPBOX_REFRESH_TOKEN=" + result.refresh_token)
    print("(Copy that line into your .env file.)")
