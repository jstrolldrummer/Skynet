"""One-time helper to mint a Dropbox refresh token.

Usage:  python -m app.dropbox_setup

Walks you through creating a Dropbox app, doing the OAuth dance once, and
prints the env-var values to paste into `.env` (or Render's secret manager).
"""
import sys
import urllib.parse

import httpx

INSTRUCTIONS = """\
Step 1 — Create the Dropbox app (one-time):

  1. Go to https://www.dropbox.com/developers/apps and click "Create app".
  2. API: "Scoped access". Access type: "App folder". Name: anything (e.g. Subtext).
  3. On the new app's page, go to the "Permissions" tab and check:
       - files.content.read
       - files.metadata.read
     Click "Submit".
  4. Back on the "Settings" tab, copy the App key and App secret below.
"""


def main() -> int:
    print(INSTRUCTIONS)
    app_key = input("App key:    ").strip()
    app_secret = input("App secret: ").strip()
    if not app_key or not app_secret:
        print("App key and secret are required.", file=sys.stderr)
        return 1

    auth_url = (
        "https://www.dropbox.com/oauth2/authorize?"
        + urllib.parse.urlencode(
            {
                "client_id": app_key,
                "response_type": "code",
                "token_access_type": "offline",
            }
        )
    )
    print(
        "\nStep 2 — Open this URL in a browser, log in, click 'Allow', "
        "then copy the access code it shows you:\n"
    )
    print(f"    {auth_url}\n")
    code = input("Access code: ").strip()
    if not code:
        print("Access code is required.", file=sys.stderr)
        return 1

    r = httpx.post(
        "https://api.dropbox.com/oauth2/token",
        data={"code": code, "grant_type": "authorization_code"},
        auth=(app_key, app_secret),
        timeout=15,
    )
    if r.status_code != 200:
        print(f"\nDropbox rejected the code ({r.status_code}): {r.text}", file=sys.stderr)
        return 1
    refresh_token = r.json().get("refresh_token", "")
    if not refresh_token:
        print(f"\nNo refresh token in response: {r.text}", file=sys.stderr)
        return 1

    print("\nDone! Add these to your .env (or Render env vars):\n")
    print(f"DROPBOX_APP_KEY={app_key}")
    print(f"DROPBOX_APP_SECRET={app_secret}")
    print(f"DROPBOX_REFRESH_TOKEN={refresh_token}")
    print("DROPBOX_FILE_PATH=/subtext.xlsx")
    print(
        "\n(DROPBOX_FILE_PATH is the filename inside Apps/<your-app>/ — "
        "change it if you named your file something else.)"
    )
    print(
        "\nThen drop your spreadsheet into the app folder Dropbox created at "
        "Apps/<your-app>/ on your computer."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
