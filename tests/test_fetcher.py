import json
import time
import pytest
import requests
from unittest.mock import patch, MagicMock
from src.fetcher import StravaClient, fetch_activities, _get_with_retry, _rate_limit_delay


def make_client():
    return StravaClient(
        client_id="123", client_secret="secret",
        access_token="token", refresh_token="refresh"
    )


def _mock_activity(activity_id, start_date="2024-01-15T08:00:00Z"):
    return {
        "id": activity_id,
        "type": "Run",
        "sport_type": "Run",
        "start_date": start_date,
        "start_date_local": start_date,
        "distance": 8000.0,
        "average_speed": 3.2,
        "total_elevation_gain": 50.0,
        "map": {"summary_polyline": "abcd"},
    }


def test_fetch_activities_paginates_until_empty(tmp_path):
    """Fetcher paginates /athlete/activities until an empty page is returned."""
    client = make_client()

    page1 = [_mock_activity(i) for i in range(3)]
    page2 = []

    responses = [
        MagicMock(**{"json.return_value": page1, "raise_for_status": MagicMock()}),
        MagicMock(**{"json.return_value": page2, "raise_for_status": MagicMock()}),
    ]

    with patch("requests.get", side_effect=responses):
        activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 3
    cache_file = tmp_path / "activities.json"
    assert cache_file.exists()
    saved = json.loads(cache_file.read_text())
    assert len(saved) == 3


def test_fetch_activities_reconciles_history_without_start_time_cursor(tmp_path):
    """A cached fetch timestamp must not hide delayed uploads."""
    existing = [_mock_activity(1, "2024-01-01T08:00:00Z")]
    cache_file = tmp_path / "activities.json"
    cache_file.write_text(json.dumps(existing))

    meta_file = tmp_path / "cache_meta.json"
    meta_file.write_text(json.dumps({"last_fetched": 1704067200, "total_count": 1}))

    new_activity = _mock_activity(2, "2023-12-31T08:00:00Z")
    responses = [
        MagicMock(**{"json.return_value": [new_activity], "raise_for_status": MagicMock()}),
        MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()}),
    ]

    client = make_client()
    with patch("requests.get", side_effect=responses) as mock_get:
        activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 2
    call_kwargs = mock_get.call_args_list[0][1]
    assert "after" not in call_kwargs["params"]
    assert {a["id"] for a in activities} == {1, 2}


def test_fetch_activities_handles_rate_limit(tmp_path):
    """On 429, fetcher sleeps and retries."""
    client = make_client()

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"X-RateLimit-Reset": str(int(time.time()) + 1)}
    rate_limited.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=rate_limited
    )

    success = MagicMock(**{
        "json.return_value": [_mock_activity(1)],
        "raise_for_status": MagicMock(),
        "status_code": 200,
    })
    empty = MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()})

    with patch("requests.get", side_effect=[rate_limited, success, empty]):
        with patch("time.sleep") as mock_sleep:
            activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 1
    mock_sleep.assert_called_once()


def test_token_refresh_updates_access_token(tmp_path):
    """When access token is expired, client refreshes it and stores new token."""
    client = StravaClient(
        client_id="123",
        client_secret="secret",
        access_token="old_token",
        refresh_token="refresh_token",
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
        "expires_at": 9999999999,
    }
    mock_response.raise_for_status = MagicMock()

    env_file = tmp_path / "refresh.env"
    env_file.write_text("STRAVA_ACCESS_TOKEN=old_token\nSTRAVA_REFRESH_TOKEN=refresh_token\n")
    default_env = tmp_path / ".env"
    default_env.write_text("STRAVA_ACCESS_TOKEN=sentinel\nSTRAVA_REFRESH_TOKEN=sentinel\n")
    original = default_env.read_bytes()
    with patch("requests.post", return_value=mock_response) as mock_post:
        client.refresh_access_token(env_file=env_file)

    assert client.access_token == "new_token"
    assert client.refresh_token == "new_refresh"
    assert "STRAVA_ACCESS_TOKEN=new_token\n" in env_file.read_text()
    assert "STRAVA_REFRESH_TOKEN=new_refresh\n" in env_file.read_text()
    assert default_env.read_bytes() == original
    mock_post.assert_called_once()


def test_fetch_activities_refreshes_token_on_401(tmp_path):
    """On 401, fetcher refreshes token and retries the request."""
    client = make_client()

    unauthorized = MagicMock()
    unauthorized.status_code = 401
    unauthorized.raise_for_status = MagicMock()

    success = MagicMock(**{
        "json.return_value": [_mock_activity(1)],
        "raise_for_status": MagicMock(),
        "status_code": 200,
    })
    empty = MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()})

    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
        "expires_at": 9999999999,
    }
    mock_post_resp.raise_for_status = MagicMock()

    with patch("requests.get", side_effect=[unauthorized, success, empty]):
        with patch("requests.post", return_value=mock_post_resp):
            with patch("src.fetcher._update_env_tokens"):
                activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 1
    assert client.access_token == "new_token"


def test_get_headers_include_bearer_token():
    client = StravaClient(
        client_id="123",
        client_secret="secret",
        access_token="mytoken",
        refresh_token="refresh",
    )
    headers = client._headers()
    assert headers["Authorization"] == "Bearer mytoken"


def test_from_env_raises_key_error_when_tokens_missing(monkeypatch):
    """StravaClient.from_env() raises KeyError if tokens not in env."""
    for key in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET",
                "STRAVA_ACCESS_TOKEN", "STRAVA_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with patch("dotenv.load_dotenv", return_value=False):
        with pytest.raises(KeyError):
            StravaClient.from_env()


@pytest.mark.parametrize("with_metadata", [False, True])
def test_refetch_updates_and_deduplicates_existing_and_paginated_ids(tmp_path, with_metadata):
    original = _mock_activity(1)
    (tmp_path / "activities.json").write_text(json.dumps([original, original]))
    if with_metadata:
        (tmp_path / "cache_meta.json").write_text(json.dumps({"last_fetched": 9999999999}))
    updated = dict(original, distance=12000)
    second = _mock_activity(2)
    responses = [MagicMock(status_code=200, **{"json.return_value": batch})
                 for batch in ([updated, second], [second], [])]
    with patch("requests.get", side_effect=responses):
        result = fetch_activities(make_client(), cache_dir=tmp_path)
    assert {a["id"]: a["distance"] for a in result} == {1: 12000, 2: 8000}
    assert len(result) == 2
    assert json.loads((tmp_path / "activities.json").read_text()) == result
    assert json.loads((tmp_path / "cache_meta.json").read_text())["total_count"] == 2


def test_delayed_upload_is_discovered_and_repeated_fetch_is_idempotent(tmp_path):
    cached = _mock_activity(1, "2026-10-02T08:00:00Z")
    delayed = _mock_activity(2, "2021-01-01T08:00:00Z")
    (tmp_path / "activities.json").write_text(json.dumps([cached]))
    (tmp_path / "cache_meta.json").write_text(json.dumps({"last_fetched": 1791000000}))

    def api(url, *, params, **kwargs):
        batch = [cached, delayed] if params["page"] == 1 else []
        if params.get("after"):
            batch = [a for a in batch if a["id"] == 1]
        return MagicMock(status_code=200, **{"json.return_value": batch})

    with patch("requests.get", side_effect=api):
        first = fetch_activities(make_client(), cache_dir=tmp_path)
        second = fetch_activities(make_client(), cache_dir=tmp_path)
    assert {a["id"] for a in first} == {1, 2}
    assert second == first


def test_strava_replaces_matching_garmin_fallback_only(tmp_path):
    fallback = dict(_mock_activity("garmin_123"), source="garmin", external_id="garmin_ping_123")
    unrelated = dict(_mock_activity("garmin_456"), source="garmin", external_id=None)
    (tmp_path / "activities.json").write_text(json.dumps([fallback, unrelated]))
    replacement = dict(_mock_activity(123), external_id="garmin_ping_123")
    responses = [MagicMock(status_code=200, **{"json.return_value": batch})
                 for batch in ([replacement, _mock_activity(789)], [])]
    with patch("requests.get", side_effect=responses):
        result = fetch_activities(make_client(), cache_dir=tmp_path)
    assert {a["id"] for a in result} == {"garmin_456", 123, 789}


def test_failed_fetch_leaves_activity_cache_and_metadata_unchanged(tmp_path):
    cache = tmp_path / "activities.json"
    meta = tmp_path / "cache_meta.json"
    cache.write_text(json.dumps([_mock_activity(1)]))
    meta.write_text('{"last_fetched": 100, "total_count": 1}')
    original = (cache.read_bytes(), meta.read_bytes())
    responses = [MagicMock(status_code=200, **{"json.return_value": [_mock_activity(2)]}),
                 requests.ConnectionError("offline")]
    with patch("requests.get", side_effect=responses):
        with pytest.raises(requests.ConnectionError):
            fetch_activities(make_client(), cache_dir=tmp_path)
    assert (cache.read_bytes(), meta.read_bytes()) == original


def test_headerless_rate_limit_waits_until_next_quarter_hour():
    now = [12 * 3600 + 60]

    def api(*args, **kwargs):
        status = 200 if now[0] >= 12 * 3600 + 900 else 429
        return MagicMock(status_code=status, headers={})

    def sleep(seconds):
        now[0] += seconds

    with patch("src.fetcher.time.time", side_effect=lambda: now[0]), \
         patch("src.fetcher.time.sleep", side_effect=sleep) as sleeping, \
         patch("requests.get", side_effect=api) as getting:
        response = _get_with_retry(make_client(), "https://example.invalid")
    assert response.status_code == 200
    sleeping.assert_called_once_with(841)
    assert getting.call_count == 2


@pytest.mark.parametrize("prefix", ["X-RateLimit", "X-ReadRateLimit"])
def test_daily_quota_waits_until_midnight_utc(prefix):
    now = 12 * 3600 + 60
    headers = {f"{prefix}-Limit": "100,1000", f"{prefix}-Usage": "1,1000",
               "X-RateLimit-Reset": str(now + 60)}
    with patch("src.fetcher.time.time", return_value=now):
        assert _rate_limit_delay(headers) == 86400 + 1 - now


def test_exhausted_rate_limit_does_not_sleep_after_last_attempt():
    with patch("requests.get", return_value=MagicMock(status_code=429, headers={})), \
         patch("src.fetcher.time.sleep") as sleeping:
        with pytest.raises(RuntimeError, match="Max retries"):
            _get_with_retry(make_client(), "https://example.invalid")
    assert sleeping.call_count == 2
