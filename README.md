# Subtext

Daily SMS follow-ups to subcontractors about their open items, with reply tracking. (Working name — repo and Render service are still "Skynet" under the hood.)

- **Stack:** Python · FastAPI · SQLite · Twilio
- **Hosting:** Render (one web service + persistent disk)
- **Daily schedule:** external cron pings `POST /tasks/send-followups`

---

## What it does

1. You upload an `.xlsx` of subs / jobs / open items in the admin web UI. (You can update it as often as you like — each upload replaces the current set.)
2. **7:30am — preview.** The app texts *you* a numbered list of who's about to be contacted. You can reply `skip 1`, `skip 1,3`, or `skip 1-3` to drop anyone, `send` to fire immediately, or `status` to recheck what's queued.
3. **8:00am — send.** Whatever is still pending goes out to subs. If you don't reply to the preview at all, everything sends as-is.
4. Sub replies hit a Twilio webhook and get logged against the sub. You read replies in the admin UI.

Sample outbound text to a sub:

```
Morning Carlos — Joe with Wyatt & Gray Custom Homes. Your open items:
1. 123 Oak St — finish drywall in master
2. 123 Oak St — punchlist photos to me
3. 47 Pine Ln — confirm Tuesday start

Reply with a quick status on each (e.g. "1 done, 2 by Friday"). Reply STOP to opt out.
```

Sample 7:30am preview text to you:

```
Subtext: 2 follow-ups queued for 8am.
1. Carlos Garcia (3 items)
2. Jim Smith (2 items)

Reply "skip 1" or "skip 1,3" to drop, "send" to fire now, "status" to recheck.
```

---

## Local setup (Mac)

```bash
git clone <repo> && cd Skynet
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in TWILIO_* once you have an account
# Set ADMIN_PASSWORD and TASK_TOKEN to anything random
# Set OWNER_PHONE to your personal cell in E.164 (e.g. +15125551234)

uvicorn app.main:app --reload
```

Open <http://localhost:8000/admin> — username is `admin`, password is whatever you set.

---

## Twilio setup

1. Create an account at <https://www.twilio.com/try-twilio> (free trial gives ~$15 credit).
2. Buy a phone number (Phone Numbers → Buy a Number, ~$1/mo).
3. Copy **Account SID** and **Auth Token** from the console home → into `.env`.
4. Put your phone number into `TWILIO_FROM_NUMBER` in E.164 format (e.g. `+15125551234`).
5. **For replies to be captured:** in Phone Numbers → Active Numbers → your number → "A message comes in", set the webhook to `https://YOUR-DEPLOYED-URL/sms/incoming` (POST). You can do this after deploying.

> Twilio trial accounts can only text **verified** numbers. To text any subcontractor, upgrade the account (add a credit card; pay-as-you-go is ~$0.008/text).

> US numbers also require **A2P 10DLC registration** (a one-time brand + campaign signup, ~$15) before high-volume sending. Twilio walks you through it.

---

## The spreadsheet

In the admin UI, click **Download template** to get a starter `.xlsx`. The format is:

| Name           | Phone         | Job              | Item                       |
|----------------|---------------|------------------|----------------------------|
| Carlos Garcia  | 512-555-1234  | 123 Oak St       | finish drywall in master   |
| Carlos Garcia  | 512-555-1234  | 123 Oak St       | punchlist photos to me     |
| Carlos Garcia  | 512-555-1234  | 47 Pine Ln       | confirm Tuesday start      |
| Jim Smith      | 512-555-9876  | 47 Pine Ln       | rough plumbing inspection  |

- **One row per open item.** A sub with three open items gets three rows.
- Same `Name` + `Phone` across rows = same sub. Same `Sub` + `Job` across rows = same job.
- Phone format is flexible (`512-555-1234`, `(512) 555-1234`, `+15125551234` all work).
- Headers are case-insensitive and tolerate variants like "Phone Number" or "Job Title".

**What an upload does:** every existing job and open item is wiped and rebuilt from the sheet. Subs are upserted by phone — existing subs and their message history are preserved. Edit the spreadsheet locally each evening, upload, done.

---

## Sending a test text

1. Put yourself in the spreadsheet as one row (Name, your phone, any job, any item) and upload.
2. Click **Send today's follow-ups now**. You should get a text within seconds.

---

## Deploying to Render

This deploys a single web service with a 1 GB persistent disk so the SQLite DB survives restarts.

1. Push this repo to GitHub (already on branch `claude/subcontractor-followup-texting-LQhPP`).
2. Sign up at <https://render.com>, click **New → Blueprint**, point it at this repo. It picks up `render.yaml`.
3. Render will prompt for the secret env vars (`TWILIO_*`, `ADMIN_PASSWORD`, `TASK_TOKEN`). Fill them in.
4. First deploy takes ~3 minutes. When it's live, you'll have a URL like `https://skynet-xxxx.onrender.com`.
5. Set the Twilio webhook (see Twilio step 5 above) to `https://skynet-xxxx.onrender.com/sms/incoming`.

The `starter` plan in `render.yaml` is $7/mo and required for the persistent disk. Free tier won't keep the DB across deploys.

---

## Setting up the daily schedule

You need **two** cron jobs: one at 7:30am to send the preview, one at 8:00am to fire whatever's still pending. Both are protected by `TASK_TOKEN`.

**Easiest: cron-job.org (free)**

1. Go to <https://cron-job.org/en/signup/> and create an account.
2. Create cronjob #1 — preview:
   - Title: `Skynet preview`
   - URL: `https://skynet-xxxx.onrender.com/tasks/preview-followups`
   - Method: `POST`
   - Schedule: every day at **7:30 AM** in your timezone
   - Headers: `X-Task-Token: <your TASK_TOKEN value>`
3. Create cronjob #2 — send:
   - Title: `Skynet send`
   - URL: `https://skynet-xxxx.onrender.com/tasks/send-pending`
   - Method: `POST`
   - Schedule: every day at **8:00 AM** in your timezone
   - Headers: `X-Task-Token: <your TASK_TOKEN value>`
4. Save and enable both.

If you ever want to bypass the preview/skip flow and just fire immediately (useful for testing), `POST /tasks/send-followups` still works — it's the original one-shot sweep.

**Alternative: Render Cron Job** — add `cron`-type services in `render.yaml` that hit the URLs with `curl`. Same idea, slightly more involved.

---

## How to use it day-to-day

- Keep one master spreadsheet of who's working on what. Each evening, edit it (add new items, delete completed ones) and upload — the morning text goes out automatically.
- When a sub replies, it shows up in the **Recent Messages** section. Mark items `done` or `blocked` based on what they say (or just remove the row from the sheet next time).
- Mark a sub inactive (Toggle) to stop their texts without deleting their history. Re-uploading a sheet that includes them will reactivate them.

---

## Weekends

By default the 7:30am preview and 8:00am send are no-ops on Saturday and Sunday in your local timezone. Set `SKIP_WEEKENDS=false` to text 7 days a week, and `TIMEZONE` to the IANA zone you operate in (default `America/Chicago`).

---

## Twilio signature validation

`/sms/incoming` verifies the `X-Twilio-Signature` header so that random callers can't spoof a sub's reply. For this to work in production, the app needs to know its own public URL. On Render, `RENDER_EXTERNAL_URL` is auto-injected, so it just works. If you deploy elsewhere, set `PUBLIC_URL` to the full base URL (e.g. `https://yourapp.example.com`). When neither is set (local dev), validation is skipped.

---

## Future ideas (not built yet)

- Holiday calendar (currently only weekends are skipped)
- Auto-parse simple replies like "1 done, 2 blocked" into item status updates
- Per-sub send time
- Email digest to you summarizing what came back each day
