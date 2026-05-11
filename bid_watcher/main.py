from __future__ import annotations

import signal
import time
from datetime import datetime, timedelta, timezone
from typing import List

from bid_watcher.classify.classifier import Classifier
from bid_watcher.config import Settings, load_settings
from bid_watcher.pipeline import Pipeline
from bid_watcher.sinks.dropbox_sink import DropboxSink
from bid_watcher.sources import EmailSource
from bid_watcher.state.store import StateStore
from bid_watcher.util.logging import configure_logging, get_logger

log = get_logger(__name__)


def _build_sources(s: Settings) -> List[EmailSource]:
    sources: List[EmailSource] = []
    if s.gmail_enabled:
        from bid_watcher.sources.gmail import GmailSource

        sources.append(
            GmailSource(
                client_secret_file=s.gmail_client_secret_file,
                token_file=s.gmail_token_file,
                account_email=s.gmail_user_email or "",
            )
        )
    if s.outlook_enabled:
        if not s.outlook_client_id:
            raise SystemExit("OUTLOOK_ENABLED but OUTLOOK_CLIENT_ID not set")
        from bid_watcher.sources.outlook import OutlookSource

        sources.append(
            OutlookSource(
                tenant_id=s.outlook_tenant_id,
                client_id=s.outlook_client_id,
                cache_file=s.outlook_token_cache_file,
                account_email=s.outlook_user_email or "",
            )
        )
    if not sources:
        raise SystemExit("No email sources enabled; set GMAIL_ENABLED or OUTLOOK_ENABLED in .env")
    return sources


def _build_sink(s: Settings) -> DropboxSink:
    missing = [k for k, v in {
        "DROPBOX_APP_KEY": s.dropbox_app_key,
        "DROPBOX_APP_SECRET": s.dropbox_app_secret,
        "DROPBOX_REFRESH_TOKEN": s.dropbox_refresh_token,
    }.items() if not v]
    if missing:
        raise SystemExit("Missing Dropbox config: " + ", ".join(missing))
    return DropboxSink(
        app_key=s.dropbox_app_key,
        app_secret=s.dropbox_app_secret,
        refresh_token=s.dropbox_refresh_token,
        estimating_root=s.dropbox_estimating_path,
    )


_stop = False


def _signal_handler(signum, frame):  # noqa: ARG001
    global _stop
    log.info("main.signal", signum=signum)
    _stop = True


def run_once(pipeline: Pipeline, sources: List[EmailSource], state: StateStore, default_lookback: timedelta) -> None:
    for src in sources:
        cursor = state.get_cursor(src.name) or (datetime.now(timezone.utc) - default_lookback)
        latest = cursor
        try:
            for email in src.fetch_since(cursor):
                try:
                    pipeline.handle_email(email)
                except Exception as e:
                    log.exception("main.email_failed", source=src.name, id=email.message_id, error=str(e))
                if email.received_at > latest:
                    latest = email.received_at
        except Exception as e:
            log.exception("main.source_failed", source=src.name, error=str(e))
            continue
        if latest > cursor:
            state.set_cursor(src.name, latest)


def main() -> None:
    configure_logging()
    s = load_settings()
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    state = StateStore(s.state_db_path)
    classifier = Classifier(api_key=s.anthropic_api_key, model=s.classifier_model)
    sink = _build_sink(s)
    sources = _build_sources(s)
    pipeline = Pipeline(s, classifier, sink, state)

    lookback = timedelta(hours=s.lookback_hours_on_first_run)
    log.info("main.starting", interval=s.poll_interval_seconds, sources=[src.name for src in sources])

    while not _stop:
        try:
            run_once(pipeline, sources, state, lookback)
        except Exception as e:
            log.exception("main.cycle_failed", error=str(e))
        for _ in range(s.poll_interval_seconds):
            if _stop:
                break
            time.sleep(1)

    log.info("main.stopped")


if __name__ == "__main__":
    main()
