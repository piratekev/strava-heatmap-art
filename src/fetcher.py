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
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        _update_env_tokens(env_file, self.access_token, self.refresh_token)

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv()
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


def _get_with_retry(client, url, params=None, max_retries=3):
    """GET request with automatic rate-limit and token-refresh retry."""
    token_refreshed = False
    for attempt in range(max_retries):
        response = requests.get(url, headers=client._headers(), params=params or {})
        if response.status_code == 429:
            reset_ts = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            sleep_secs = max(reset_ts - time.time(), 1)
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
    """Fetch all activities with incremental caching. Returns full list."""
    from config import STRAVA_BASE_URL, STRAVA_ACTIVITIES_PER_PAGE

    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "activities.json")
    meta_file = os.path.join(cache_dir, "cache_meta.json")

    # Load existing cache
    existing = []
    last_fetched = None
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            existing = json.load(f)
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            meta = json.load(f)
            last_fetched = meta.get("last_fetched")

    # Fetch new activities
    new_activities = []
    page = 1
    fetch_time = int(time.time())

    while True:
        params = {"per_page": STRAVA_ACTIVITIES_PER_PAGE, "page": page}
        if last_fetched:
            params["after"] = last_fetched

        response = _get_with_retry(
            client, f"{STRAVA_BASE_URL}/athlete/activities", params=params
        )
        batch = response.json()
        if not batch:
            break
        new_activities.extend(batch)
        page += 1

    all_activities = existing + new_activities

    # Save cache
    with open(cache_file, "w") as f:
        json.dump(all_activities, f)
    with open(meta_file, "w") as f:
        json.dump({"last_fetched": fetch_time, "total_count": len(all_activities)}, f)

    if new_activities:
        print(f"Fetched {len(new_activities)} new activities. Total: {len(all_activities)}")
    else:
        print(f"No new activities. Total cached: {len(all_activities)}")

    return all_activities
