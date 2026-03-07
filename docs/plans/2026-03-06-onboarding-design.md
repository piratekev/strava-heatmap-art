# Onboarding & Auth Design

**Date:** 2026-03-06

## Goal

Make the repo usable by a friend running it for a different city (e.g. New York). Three deliverables:

1. `auth.py` — reads credentials from `.env`, writes tokens back to `.env`, validates before opening browser, gives clear completion message
2. `README.md` — setup guide for a new user
3. `CLAUDE.md` — architecture reference and how-to for Claude (and developers)

Plus a `.env.example` template.

---

## auth.py Changes

**Current behaviour:** takes `--client-id` / `--client-secret` as CLI args, saves tokens to `strava_creds.json`.

**New behaviour:**
- Drop argparse entirely.
- Call `load_dotenv()` and read `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` from env.
- If either is missing, print a clear error pointing to `.env.example` and `sys.exit(1)` — no browser opened.
- After successful OAuth, write all 4 tokens into `.env` (upsert: update existing lines or append if key absent). Reuse logic similar to `fetcher._update_env_tokens` but extended to handle missing keys.
- Terminal success message: "✓ Auth complete. Tokens saved to .env\n  Run: python export.py --fetch"

**export.py validation:**
- At startup (before opening `data/activities.json`), if `--fetch` is passed, call `StravaClient.from_env()` inside a try/except `KeyError` and print a friendly message pointing to `auth.py` if tokens are missing.

---

## .env.example

```
# Strava API credentials — get these from https://www.strava.com/settings/api
STRAVA_CLIENT_ID=your_client_id_here
STRAVA_CLIENT_SECRET=your_client_secret_here

# These are written automatically by auth.py — do not edit manually
STRAVA_ACCESS_TOKEN=
STRAVA_REFRESH_TOKEN=
```

---

## README.md Structure

1. Title + `sf.png` preview image
2. What this is (one paragraph)
3. Prerequisites
4. Setup (venv + deps + copy .env.example)
5. Strava API setup (numbered: create app, set callback domain, copy credentials)
6. Authenticate (`python auth.py` — browser opens → authorize → auto-redirected → tokens saved)
7. Fetch & render (first run, subsequent, preview)
8. Adapting for a new city (`SF_BOUNDS`, canvas size, Mercator ratio constraint, bboxfinder.com link)
9. Tweaking visuals (table of config knobs)

---

## CLAUDE.md Structure

1. Project overview + pipeline summary
2. File-by-file architecture
3. Adding a new city (what to change and why)
4. Config knobs reference (safe ranges, interactions)
5. Key implementation notes (float32 accumulation, bloom design, density expand pass order)
