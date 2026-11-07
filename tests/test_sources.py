import pytest

import config
from src import sources


def test_default_fetch_source_is_strava():
    assert config.FETCH_SOURCE == "strava"


def test_dispatches_to_garmin(monkeypatch):
    import src.garmin as garmin
    calls = []
    monkeypatch.setattr(garmin, "login", lambda: "api")
    monkeypatch.setattr(garmin, "fetch_garmin_activities", lambda api: calls.append(api))
    sources.fetch_from_source("garmin")
    assert calls == ["api"]


def test_dispatches_to_strava(monkeypatch):
    import src.fetcher as fetcher
    calls = []
    monkeypatch.setattr(fetcher.StravaClient, "from_env", classmethod(lambda cls: "client"))
    monkeypatch.setattr(fetcher, "fetch_activities", lambda client: calls.append(client))
    sources.fetch_from_source("strava")
    assert calls == ["client"]


def test_unknown_source_exits():
    with pytest.raises(SystemExit):
        sources.fetch_from_source("fitbit")
