# Skynet

Daily SMS follow-ups to subcontractors about their open items, with reply tracking.

- **Stack:** Python · FastAPI · SQLite · Twilio
- **Hosting:** Render (one web service + persistent disk)
- **Daily schedule:** external cron pings `POST /tasks/send-followups`

---

## What it does

1. You add subcontractors, jobs, and open items in a small admin web UI.
2. Once a day, a scheduled HTTP request triggers a sweep: every active sub with at least one open item gets a single text listing their items.
3. Replies hit a Twilio webhook and get logged against the sub. You read replies in the same admin UI.

Sample outbound text:

```
Morning Carlos — Wyatt with Gray Custom Homes. Your open items:
1. 123 Oak St — finish drywall in master
2. 123 Oak St — punchlist photos to me
3. 47 Pine Ln — confirm Tuesday start

Reply with a quick status on each (e.g. "1 done, 2 by Friday"). Reply STOP to opt out.
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

## Sending a test text

1. Add yourself as a subcontractor in `/admin`.
2. Add a job pointed at yourself.
3. Add an open item under that job.
4. Click **Send today's follow-ups now**. You should get a text within seconds.

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

The app exposes `POST /tasks/send-followups` protected by `TASK_TOKEN`. Hit it once a day from any scheduler.

**Easiest: cron-job.org (free)**

1. Go to <https://cron-job.org/en/signup/> and create an account.
2. Create a new cronjob:
   - URL: `https://skynet-xxxx.onrender.com/tasks/send-followups`
   - Method: `POST`
   - Schedule: every day at the time you want (e.g. 8:00 AM, your timezone)
   - Headers: add `X-Task-Token: <your TASK_TOKEN value>`
3. Save and enable.

**Alternative: Render Cron Job** — add a second service in `render.yaml` of type `cron` that hits the URL with `curl`. Same idea, slightly more involved.

---

## How to use it day-to-day

- Add subs and active jobs as you go.
- Each evening (or whenever), drop new open items under the relevant job. The morning text goes out automatically.
- When a sub replies, it shows up in the **Recent Messages** section. Mark items `done` or `blocked` based on what they say.
- Mark a sub inactive (Toggle) to stop their texts without deleting their history.

---

## Future ideas (not built yet)

- Twilio request signature validation on `/sms/incoming` (currently unverified — easy to add)
- Don't text on weekends / holidays
- Auto-parse simple replies like "1 done, 2 blocked"
- Per-sub send time
- Email digest to you summarizing what came back each day
