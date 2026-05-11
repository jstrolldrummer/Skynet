from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    classifier_model: str = Field("claude-sonnet-4-6", alias="CLASSIFIER_MODEL")
    drafter_model: str = Field("claude-sonnet-4-6", alias="DRAFTER_MODEL")

    poll_interval_seconds: int = Field(180, alias="POLL_INTERVAL_SECONDS")
    lookback_hours_on_first_run: int = Field(24, alias="LOOKBACK_HOURS_ON_FIRST_RUN")

    gmail_enabled: bool = Field(False, alias="GMAIL_ENABLED")
    gmail_client_secret_file: Path = Field(Path("./secrets/client_secret_gmail.json"), alias="GMAIL_CLIENT_SECRET_FILE")
    gmail_token_file: Path = Field(Path("./secrets/gmail_token.json"), alias="GMAIL_TOKEN_FILE")
    gmail_user_email: Optional[str] = Field(None, alias="GMAIL_USER_EMAIL")

    outlook_enabled: bool = Field(False, alias="OUTLOOK_ENABLED")
    outlook_tenant_id: str = Field("common", alias="OUTLOOK_TENANT_ID")
    outlook_client_id: Optional[str] = Field(None, alias="OUTLOOK_CLIENT_ID")
    outlook_token_cache_file: Path = Field(Path("./secrets/outlook_token_cache.json"), alias="OUTLOOK_TOKEN_CACHE_FILE")
    outlook_user_email: Optional[str] = Field(None, alias="OUTLOOK_USER_EMAIL")

    dropbox_app_key: Optional[str] = Field(None, alias="DROPBOX_APP_KEY")
    dropbox_app_secret: Optional[str] = Field(None, alias="DROPBOX_APP_SECRET")
    dropbox_refresh_token: Optional[str] = Field(None, alias="DROPBOX_REFRESH_TOKEN")
    dropbox_estimating_path: str = Field("/Wyatt and Gray/Estimating", alias="DROPBOX_ESTIMATING_PATH")

    proposal_template_path: Path = Field(Path("./templates/proposal_template.docx"), alias="PROPOSAL_TEMPLATE_PATH")
    local_mirror_dir: Optional[Path] = Field(None, alias="LOCAL_MIRROR_DIR")

    # Sender / company info that fills the cover page
    sender_name: str = Field("Joe Stroll", alias="SENDER_NAME")
    sender_company: str = Field("Wyatt + Gray Custom Homes LLC", alias="SENDER_COMPANY")
    sender_phone: str = Field("(475) 747-1804", alias="SENDER_PHONE")
    sender_email: str = Field("Joe@WyattGrayHomes.com", alias="SENDER_EMAIL")
    sender_address: str = Field("336 Rock Rimmon Rd, Stamford, CT 06903, USA", alias="SENDER_ADDRESS")

    state_db_path: Path = Field(Path("./data/state.sqlite3"), alias="STATE_DB_PATH")

    never_reply: bool = Field(True, alias="NEVER_REPLY")


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
