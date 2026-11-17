import os
import urllib.request

import pytest
import requests


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Keep tests away from the user's credentials, caches, and network."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for key in list(os.environ):
        if key.startswith(("STRAVA_", "GARMIN_")):
            monkeypatch.delenv(key, raising=False)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("Tests must mock external network requests")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_network)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected_network)
