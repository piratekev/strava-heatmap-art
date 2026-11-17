import json
import os
import time
import requests
from config import STRAVA_TOKEN_URL


class StravaClient:
    def __init__(self, client_id, client_secret, access_token, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def refresh_access_token(self, env_file=".env"):
        response = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        _update_env_tokens(env_file, self.access_token, self.refresh_token)

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(".env")
        return cls(
            client_id=os.environ["STRAVA_CLIENT_ID"],
            client_secret=os.environ["STRAVA_CLIENT_SECRET"],
            access_token=os.environ["STRAVA_ACCESS_TOKEN"],
            refresh_token=os.environ["STRAVA_REFRESH_TOKEN"],
        )


def _update_env_tokens(env_file, access_token, refresh_token):
    """Write updated tokens back to .env so they persist across runs."""
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        lines = f.readlines()
    updated = []
    for line in lines:
        if line.startswith("STRAVA_ACCESS_TOKEN="):
            updated.append(f"STRAVA_ACCESS_TOKEN={access_token}\n")
        elif line.startswith("STRAVA_REFRESH_TOKEN="):
            updated.append(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")
        else:
            updated.append(line)
    with open(env_file, "w") as f:
        f.writelines(updated)


def _rate_limit_delay(headers):
    """Wait for the applicable Strava quota window, not an assumed 60 seconds."""
    now = time.time()
    reset = (int(now) // 900 + 1) * 900 + 1
    daily_reset = 0
    for prefix in ("X-RateLimit", "X-ReadRateLimit"):
        try:
            limits = [int(n) for n in headers[f"{prefix}-Limit"].split(",")]
            usage = [int(n) for n in headers[f"{prefix}-Usage"].split(",")]
            if usage[1] >= limits[1]:
                daily_reset = (int(now) // 86400 + 1) * 86400 + 1
        except (KeyError, ValueError, IndexError):
            continue
    try:
        reset = max(now + 1, float(headers["X-RateLimit-Reset"]))
    except (KeyError, ValueError):
        pass
    return max(reset, daily_reset) - now


def _get_with_retry(client, url, params=None, max_retries=3):
    """GET request with automatic rate-limit and token-refresh retry."""
    token_refreshed = False
    for attempt in range(max_retries):
        response = requests.get(url, headers=client._headers(), params=params or {}, timeout=30)
        if response.status_code == 429:
            if attempt == max_retries - 1:
                break
            sleep_secs = _rate_limit_delay(response.headers)
            print(f"Rate limited. Sleeping {sleep_secs:.0f}s...")
            time.sleep(sleep_secs)
            continue
        if response.status_code == 401 and not token_refreshed:
            print("Access token expired. Refreshing...")
            client.refresh_access_token()
            token_refreshed = True
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("Max retries exceeded")


def fetch_activities(client, cache_dir="data"):
    """Reconcile the full Strava history by ID, including delayed uploads."""
    from config import STRAVA_BASE_URL, STRAVA_ACTIVITIES_PER_PAGE

    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "activities.json")
    meta_file = os.path.join(cache_dir, "cache_meta.json")

    # Load existing cache
    existing = []
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            existing = json.load(f)
    # `after` filters activity start times, not upload times. Scan every page so
    # offline uploads and edits to old activities are never hidden by a cursor.
    new_activities = []
    page = 1
    fetch_time = int(time.time())

    while True:
        params = {"per_page": STRAVA_ACTIVITIES_PER_PAGE, "page": page}
        response = _get_with_retry(
            client, f"{STRAVA_BASE_URL}/athlete/activities", params=params
        )
        batch = response.json()
        if not batch:
            break
        new_activities.extend(batch)
        page += 1

    # Strava copies supersede any Garmin-fallback entries for the same activity
    new_external_ids = {a["external_id"] for a in new_activities if a.get("external_id")}
    existing = [a for a in existing
                if not (a.get("source") == "garmin" and a.get("external_id") in new_external_ids)]
    by_id = {a["id"]: a for a in existing}
    added_count = len({a["id"] for a in new_activities} - by_id.keys())
    by_id.update((a["id"], a) for a in new_activities)
    all_activities = list(by_id.values())

    # Save cache
    with open(cache_file, "w") as f:
        json.dump(all_activities, f)
    with open(meta_file, "w") as f:
        json.dump({"last_fetched": fetch_time, "total_count": len(all_activities)}, f)

    print(f"Reconciled {len({a['id'] for a in new_activities})} Strava activities, "
          f"{added_count} new. Total cached: {len(all_activities)}")

    return all_activities
