#!/usr/bin/env python3
"""
Strava OAuth — run once to get your tokens.

Reads STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET from .env.
After you authorize in the browser, tokens are saved back to .env automatically.
"""
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

AUTH_CODE = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            AUTH_CODE = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Auth successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code found. Try again.</h2>")

    def log_message(self, format, *args):
        pass  # suppress server logs


def _check_env_credentials():
    """Exit with a clear message if CLIENT_ID or CLIENT_SECRET are missing."""
    missing = [k for k in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        print("ERROR: Missing required environment variables:", ", ".join(missing))
        print("Copy .env.example to .env and fill in your Strava API credentials.")
        print("Get them from: https://www.strava.com/settings/api")
        sys.exit(1)


def _upsert_env_tokens(env_file, access_token, refresh_token):
    """Write ACCESS_TOKEN and REFRESH_TOKEN into env_file.

    Updates lines if the keys already exist, appends them if not.
    Creates the file if it doesn't exist.
    """
    lines = []
    if os.path.exists(env_file):
        with open(env_file) as f:
            lines = f.readlines()

    updated_access = False
    updated_refresh = False
    result = []
    for line in lines:
        if line.startswith("STRAVA_ACCESS_TOKEN="):
            result.append(f"STRAVA_ACCESS_TOKEN={access_token}\n")
            updated_access = True
        elif line.startswith("STRAVA_REFRESH_TOKEN="):
            result.append(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")
            updated_refresh = True
        else:
            result.append(line)

    if not updated_access:
        result.append(f"STRAVA_ACCESS_TOKEN={access_token}\n")
    if not updated_refresh:
        result.append(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")

    with open(env_file, "w") as f:
        f.writelines(result)


def main():
    load_dotenv()
    _check_env_credentials()

    client_id = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri=http://localhost:8765"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )

    server = HTTPServer(("localhost", 8765), CallbackHandler)
    t = threading.Thread(target=server.handle_request)
    t.start()

    print("Opening Strava in your browser...")
    print("Click 'Authorize' on the Strava page. The browser will redirect to localhost")
    print("and show 'Auth successful' — then come back here.")
    webbrowser.open(auth_url)
    t.join()

    if not AUTH_CODE:
        print("ERROR: Did not receive auth code.")
        sys.exit(1)

    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": AUTH_CODE,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    _upsert_env_tokens(".env", tokens["access_token"], tokens["refresh_token"])

    print("Auth complete. Tokens saved to .env")
    print(f"  Athlete: {tokens['athlete']['firstname']} {tokens['athlete']['lastname']}")
    print(f"  Run: python render.py --fetch")


if __name__ == "__main__":
    main()
