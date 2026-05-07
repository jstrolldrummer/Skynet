# Skynet — CT Flip Watch

Daily monitor for $1M+ flip candidates in Greenwich, Stamford, Darien, New Canaan, and Norwalk.
Pulls active listings from the unofficial Zillow API, scores them on a weighted formula,
uses Claude vision to estimate rehab from photos, and emails you a ranked digest each morning.

## How it works

Every morning at 7am ET (via GitHub Actions cron), the pipeline:

1. **Fetches** all active $1M+ houses across the five towns from Zillow.
2. **Stores** them in SQLite (`data/listings.db`) with full price history.
3. **Scores** each listing 0–100 across five weighted signals:
   - **70% rule** (luxury-adjusted to 82%): `(ARV × 0.82) − rehab − selling costs`
   - **Price/sqft vs. town median**
   - **Days on market** (longer = more leverage)
   - **Distressed signals** in description (estate sale, as-is, fixer, etc.)
   - **Price drop history** (how many cuts, total %)
4. **Estimates rehab** with Claude vision — sends 5 listing photos + description and
   gets back a condition tier (turnkey → gut) and $/sqft estimate.
5. **Emails** the top-ranked deals as an HTML digest.

## Setup

### 1. Get API keys

- **RapidAPI / Zillow**: sign up at https://rapidapi.com, subscribe to "Zillow.com" by apimaker
  (free tier = ~100 requests/month, enough for daily polling of 5 small towns).
- **Anthropic**: get a key at https://console.anthropic.com.
- **Gmail app password**: https://myaccount.google.com/apppasswords (needed for SMTP).

### 2. Local test run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your keys

# Dry run — skips vision API and email, writes preview to data/digest_preview.html
python -m src.main --dry-run

# Real run, but write digest to file instead of emailing
python -m src.main --no-email

# Full run
python -m src.main
```

### 3. Deploy as a daily cron

Push this repo to GitHub, then add these secrets at
**Settings → Secrets and variables → Actions**:

- `RAPIDAPI_KEY`, `RAPIDAPI_HOST`
- `ANTHROPIC_API_KEY`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `DIGEST_TO`, `DIGEST_FROM`

The workflow in `.github/workflows/daily.yml` runs at 11:00 UTC every day. You can also
trigger it manually from the Actions tab to test.

## Tuning

Edit `config.yaml` to adjust:
- Towns, price range, min beds
- Score weights (currently: 30% deal math, 25% $/sqft, 20% distress signals, 15% DOM, 10% drops)
- Luxury multiplier (default 0.82, vs. 0.70 for typical flips)
- Default rehab cost per sqft when vision fails ($75)
- Min score threshold to alert (60) and how many to include (top 10)
- Distressed keyword list

## Caveats

- **ARV is directional only.** It's calculated from active comps, not sold comps. Real flip math
  requires sold-comp data from MLS / RentCast / ATTOM (~$50/mo). Treat the score as a
  filter, not a green light.
- **Unofficial Zillow API breaks occasionally.** Zillow blocks scrapers; the RapidAPI
  endpoint is the most reliable unofficial path but expect occasional outages.
- **Always verify in person.** This tool surfaces candidates. It does not replace
  driving the property, getting contractor bids, and pulling permits.

## Repo layout

```
config.yaml              — towns, price range, scoring weights
.env.example             — required environment variables
src/fetch.py             — Zillow RapidAPI client
src/db.py                — SQLite layer (listings + price history)
src/analyze.py           — scoring + Claude vision rehab estimation
src/digest.py            — HTML email builder + SMTP send
src/main.py              — orchestrator
.github/workflows/daily.yml — daily cron job
```
