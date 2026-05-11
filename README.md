# Bid Watcher

Polls Wyatt & Gray's Gmail and Outlook inboxes for bid requests (emails sharing a
scope of work, drawings, or an invitation to bid). When one arrives:

1. Claude classifies the email and extracts client / project / due date / scope.
2. A new project folder is created inside your existing Dropbox `Estimating` tree:
   `Estimating/<Client> - <Project>/{Drawings, Scope, Correspondence, Proposal}/`.
3. All attachments are uploaded (drawings → `Drawings/`, docs/spreadsheets →
   `Scope/`), the email body lands in `Correspondence/`.
4. A draft proposal `.docx` is generated from your template and saved to
   `Proposal/`.

The service **never** replies to email or sends anything outbound. Output is
files in your Dropbox folder only.

## Architecture

```
bid_watcher/
├── main.py              # Poll loop, signal handling
├── pipeline.py          # Orchestration: classify → scaffold → draft
├── config.py            # .env-backed settings
├── models.py            # IncomingEmail, BidClassification dataclasses
├── classify/classifier.py   # Claude-based bid triage
├── proposal/drafter.py      # Fill .docx template
├── sources/
│   ├── gmail.py         # Gmail API source
│   └── outlook.py       # Microsoft Graph source
├── sinks/dropbox_sink.py    # Folder scaffolding + uploads
└── state/store.py       # sqlite: processed-message + per-source cursor
```

## Setup

### 1. Python environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Open `.env` and at minimum fill:

- `ANTHROPIC_API_KEY`
- The Dropbox section
- One or both email sections

### 2. Gmail (Wyatt & Gray gmail account)

1. In Google Cloud Console, create an OAuth client (type *Desktop app*) for the
   Gmail API. Download the JSON to `./secrets/client_secret_gmail.json`.
2. Set `GMAIL_USER_EMAIL` to the Wyatt & Gray address in `.env`.
3. Run once to authorize:

   ```bash
   bid-watcher-auth-gmail
   ```

   A browser tab will open — sign in with the W&G account and approve. A
   refresh token is written to `./secrets/gmail_token.json`.

### 3. Outlook (Wyatt & Gray Microsoft 365)

1. Register an Azure AD app (type *Public client / Mobile and desktop*) with
   delegated permission `Mail.Read`. Copy the Application (client) ID into
   `OUTLOOK_CLIENT_ID` in `.env`.
2. Run once to authorize via device flow:

   ```bash
   bid-watcher-auth-outlook
   ```

   Follow the printed instructions. A token cache is written to
   `./secrets/outlook_token_cache.json`.

### 4. Dropbox

1. In <https://www.dropbox.com/developers/apps>, create a Scoped App with
   `files.content.write` and `files.content.read`.
2. Copy the App key and App secret into `.env`.
3. Mint a refresh token:

   ```bash
   bid-watcher-auth-dropbox
   ```

   Paste the printed `DROPBOX_REFRESH_TOKEN=…` line into `.env`.
4. Set `DROPBOX_ESTIMATING_PATH` to your existing folder path
   (e.g. `/Wyatt and Gray/Estimating`).

### 5. Proposal template

Drop your standard proposal Word doc at `./templates/proposal_template.docx`.
Use these placeholders anywhere in the document — they will be replaced when
the draft is generated:

| Placeholder            | Replaced with                              |
| ---------------------- | ------------------------------------------ |
| `{{CLIENT_COMPANY}}`   | Detected client / company                  |
| `{{CONTACT_NAME}}`     | Detected contact (else sender's name)      |
| `{{CONTACT_EMAIL}}`    | Sender's email address                     |
| `{{PROJECT_NAME}}`     | Detected project name                      |
| `{{PROJECT_LOCATION}}` | Detected project location                  |
| `{{DUE_DATE}}`         | Bid due date (ISO) if found                |
| `{{SCOPE_SUMMARY}}`    | 2–5 sentence summary of the scope          |
| `{{TRADES}}`           | Comma-separated detected trades            |
| `{{TODAY}}`            | Today's date (ISO)                         |
| `{{RECEIVED_DATE}}`    | Date the email was received                |
| `{{SUBJECT}}`          | Original email subject                     |

If the template is missing, a minimal fallback `.docx` is generated so you
never lose information.

## Run

```bash
bid-watcher
```

The first cycle looks back `LOOKBACK_HOURS_ON_FIRST_RUN` hours; subsequent
cycles use the per-source cursor in `data/state.sqlite3`.

### Running as a background service (Linux/systemd)

A sample unit:

```ini
[Unit]
Description=Wyatt & Gray bid watcher
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/skynet
EnvironmentFile=/opt/skynet/.env
ExecStart=/opt/skynet/.venv/bin/bid-watcher
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
```

On macOS, wrap the same command in a `launchd` plist; on Windows, a Scheduled
Task triggered "at startup".

## Tests

```bash
pip install pytest
pytest -q
```

The smoke tests cover folder-name sanitization and the classifier's JSON
extraction.

## Safety notes

- `NEVER_REPLY=true` is hard-coded into the OAuth scopes — Gmail is granted
  `gmail.readonly` only, Outlook only `Mail.Read`. Even if the flag were
  flipped, the app could not send mail.
- Processed message IDs are tracked in sqlite so the same email is never
  scaffolded twice, even after a restart.
- Confidence threshold for scaffolding is 0.5 — adjust in `pipeline.py` if
  you want to be more or less aggressive.
