"""Dispatch --fetch to the activity source chosen by config.FETCH_SOURCE."""
import sys


def fetch_from_source(source):
    """Fetch new activities from `source` ("strava" or "garmin") into the cache."""
    if source == "strava":
        from src.fetcher import StravaClient, fetch_activities
        print("Fetching activities from Strava...")
        try:
            client = StravaClient.from_env()
        except KeyError as e:
            print(f"ERROR: Missing token {e} in .env")
            print("Run 'python auth.py' first to authenticate with Strava.")
            sys.exit(1)
        fetch_activities(client)
    elif source == "garmin":
        from src.garmin import fetch_garmin_activities, login
        print("Fetching activities from Garmin Connect...")
        fetch_garmin_activities(login())
    else:
        sys.exit(f"ERROR: unknown FETCH_SOURCE {source!r} (expected 'strava' or 'garmin')")
