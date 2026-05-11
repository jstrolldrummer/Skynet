from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bid_watcher.classify.classifier import Classifier
from bid_watcher.config import Settings
from bid_watcher.models import BidClassification, IncomingEmail
from bid_watcher.proposal.drafter import render_proposal
from bid_watcher.sinks.dropbox_sink import DropboxSink, build_project_folder_name, sanitize_segment
from bid_watcher.state.store import StateStore
from bid_watcher.util.logging import get_logger

log = get_logger(__name__)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        classifier: Classifier,
        dropbox_sink: DropboxSink,
        state: StateStore,
    ) -> None:
        self.s = settings
        self.classifier = classifier
        self.sink = dropbox_sink
        self.state = state

    def handle_email(self, email: IncomingEmail) -> Optional[str]:
        """Classify and, if a bid request, scaffold the folder and draft the proposal.

        Returns the Dropbox folder path when a folder was created, else None.
        """
        if self.state.is_processed(email.source, email.message_id):
            log.debug("pipeline.already_processed", source=email.source, id=email.message_id)
            return None

        log.info(
            "pipeline.email",
            source=email.source,
            sender=email.sender_email,
            subject=email.subject,
            attachments=len(email.attachments),
        )

        classification = self.classifier.classify(email)
        log.info(
            "pipeline.classified",
            is_bid=classification.is_bid_request,
            confidence=classification.confidence,
            client=classification.client_company,
            project=classification.project_name,
        )

        folder_path: Optional[str] = None
        if classification.is_bid_request and classification.confidence >= 0.5:
            folder_path = self._scaffold_and_populate(email, classification)
        else:
            log.info("pipeline.skipped_not_bid", subject=email.subject)

        self.state.mark_processed(
            email.source,
            email.message_id,
            email.account_email,
            classification.is_bid_request,
            folder_path,
        )
        return folder_path

    def _scaffold_and_populate(self, email: IncomingEmail, c: BidClassification) -> str:
        folder_name = build_project_folder_name(c.client_company, c.project_name, email.received_at.isoformat())
        project_path = self.sink.create_project_skeleton(folder_name)

        # Save email body
        body_text = f"From: {email.sender_name or ''} <{email.sender_email}>\n"
        body_text += f"Subject: {email.subject}\n"
        body_text += f"Received: {email.received_at.isoformat()}\n\n"
        body_text += email.body_text
        self.sink.upload_bytes(f"{project_path}/Correspondence/original_email.txt", body_text.encode("utf-8"))

        # Land each attachment
        for att in email.attachments:
            subfolder = self.sink.classify_attachment(att.filename)
            safe = sanitize_segment(att.filename, max_len=120)
            self.sink.upload_bytes(f"{project_path}/{subfolder}/{safe}", att.content)

        # Draft proposal
        try:
            docx_bytes = render_proposal(self.s.proposal_template_path, email, c, self.s)
            self.sink.upload_bytes(
                f"{project_path}/Proposal/{sanitize_segment(folder_name)} - PROPOSAL DRAFT.docx",
                docx_bytes,
            )
        except Exception as e:
            log.exception("pipeline.proposal_failed", error=str(e))

        return project_path
