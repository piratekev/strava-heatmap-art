"""Garmin Connect fallback fetcher.

Converts Garmin activities into the subset of the Strava activity schema the
pipeline reads (sport_type, map.summary_polyline, id, start_date, distance,
average_speed, total_elevation_gain) and appends them to data/activities.json.
"""
import json
import os
from datetime import datetime, timezone

import polyline as pl

GARMIN_TOKENSTORE = "~/.garminconnect"


def _parse_gmt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def garmin_to_strava(summary, details):
    """Map a Garmin activity summary + details response to a Strava-shaped dict.

    Returns None if the activity isn't a run or has no GPS track.
    """
    type_key = (summary.get("activityType") or {}).get("typeKey", "")
    if "running" not in type_key:
        return None
    points = ((details or {}).get("geoPolylineDTO") or {}).get("polyline") or []
    coords = [(p["lat"], p["lon"]) for p in points if p.get("lat") is not None and p.get("lon") is not None]
    if not coords:
        return None

    garmin_id = summary["activityId"]
    start = _parse_gmt(summary["startTimeGMT"])
    return {
        "source": "garmin",
        "id": f"garmin_{garmin_id}",
        "external_id": f"garmin_ping_{garmin_id}",
        "name": summary.get("activityName", ""),
        "type": "Run",
        "sport_type": "Run",
        "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_date_local": summary.get("startTimeLocal", "").replace(" ", "T") + "Z",
        "distance": summary.get("distance") or 0.0,
        "moving_time": summary.get("movingDuration") or summary.get("duration") or 0,
        "elapsed_time": summary.get("elapsedDuration") or summary.get("duration") or 0,
        "average_speed": summary.get("averageSpeed") or 0.0,
        "total_elevation_gain": summary.get("elevationGain") or 0.0,
        "start_latlng": list(coords[0]),
        "end_latlng": list(coords[-1]),
        "map": {"id": f"g{garmin_id}", "summary_polyline": pl.encode(coords)},
    }


def _start_ts(act):
    return datetime.strptime(act["start_date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def merge_new(existing, new):
    """Return the activities in `new` not already present in `existing`.

    Matches on Garmin activity ID (Strava's external_id carries it) and, as a
    fallback, on start time within 60s.
    """
    known_ids = {a.get("external_id") for a in existing if a.get("external_id")}
    known_starts = [_start_ts(a) for a in existing if a.get("start_date")]
    out = []
    for act in new:
        if act["external_id"] in known_ids:
            continue
        ts = _start_ts(act)
        if any(abs(ts - k) < 60 for k in known_starts):
            continue
        out.append(act)
        known_ids.add(act["external_id"])
        known_starts.append(ts)
    return out


def login(mfa_code=None):
    """Log in from saved tokens, else credentials.

    Without a TTY (e.g. Claude Code's `!` prompt), MFA is two-step: the first
    run saves the pending login and exits; rerun with the emailed code.
    """
    import sys
    from getpass import getpass
    from garminconnect import Garmin, GarminConnectAuthenticationError

    tokenstore = os.path.expanduser(GARMIN_TOKENSTORE)
    pending_file = os.path.join(tokenstore, "mfa_pending.json")
    os.makedirs(tokenstore, mode=0o700, exist_ok=True)

    if mfa_code:
        if not os.path.exists(pending_file):
            sys.exit("No pending Garmin login — run without --mfa first.")
        with open(pending_file) as f:
            state = json.load(f)
        api = Garmin()
        api.resume_login(state, mfa_code)
        api.client.dump(tokenstore)
        os.remove(pending_file)
        return api

    try:
        api = Garmin()
        api.login(tokenstore)
        return api
    except (GarminConnectAuthenticationError, FileNotFoundError):
        pass

    interactive = sys.stdin.isatty()
    email = os.environ.get("GARMIN_EMAIL") or (interactive and input("Garmin email: "))
    password = os.environ.get("GARMIN_PASSWORD") or (interactive and getpass("Garmin password: "))
    if not (email and password):
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env (no TTY to prompt).")

    if interactive:
        api = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: "))
        api.login(tokenstore)
        return api

    api = Garmin(email, password, return_on_mfa=True)
    status, state = api.login(tokenstore)
    if status == "needs_mfa":
        fd = os.open(pending_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        sys.exit("Garmin sent an MFA code. Rerun with: garmin_fetch.py --mfa <code>")
    api.client.dump(tokenstore)
    return api


def fetch_garmin_activities(api, cache_dir="data", start_date=None):
    """Fetch Garmin runs since the latest cached activity and append them to the cache."""
    cache_file = os.path.join(cache_dir, "activities.json")
    with open(cache_file) as f:
        existing = json.load(f)

    if start_date is None:
        latest = max(a["start_date"] for a in existing if a.get("start_date"))
        start_date = latest[:10]

    summaries = api.get_activities_by_date(start_date, sortorder="asc")
    converted = []
    for s in summaries:
        if "running" not in (s.get("activityType") or {}).get("typeKey", ""):
            continue
        act = garmin_to_strava(s, api.get_activity_details(s["activityId"]))
        if act:
            converted.append(act)

    added = merge_new(existing, converted)
    if added:
        with open(cache_file, "w") as f:
            json.dump(existing + added, f)
    print(f"Garmin: {len(summaries)} activities since {start_date}, "
          f"{len(converted)} GPS runs, {len(added)} new. Total: {len(existing) + len(added)}")
    return existing + added
