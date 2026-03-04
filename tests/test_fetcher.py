import json
import time
import pytest
import requests
from unittest.mock import patch, MagicMock
from src.fetcher import StravaClient, fetch_activities


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


def test_fetch_activities_incremental_appends_new(tmp_path):
    """Second fetch only fetches activities after last_fetched and appends them."""
    existing = [_mock_activity(1, "2024-01-01T08:00:00Z")]
    cache_file = tmp_path / "activities.json"
    cache_file.write_text(json.dumps(existing))

    meta_file = tmp_path / "cache_meta.json"
    meta_file.write_text(json.dumps({"last_fetched": 1704067200, "total_count": 1}))

    new_activity = _mock_activity(2, "2024-02-01T08:00:00Z")
    responses = [
        MagicMock(**{"json.return_value": [new_activity], "raise_for_status": MagicMock()}),
        MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()}),
    ]

    client = make_client()
    with patch("requests.get", side_effect=responses) as mock_get:
        activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 2
    # Verify `after` param was used
    call_kwargs = mock_get.call_args_list[0][1]
    assert "after" in call_kwargs.get("params", {})


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


def test_token_refresh_updates_access_token():
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

    with patch("requests.post", return_value=mock_response) as mock_post:
        client.refresh_access_token()

    assert client.access_token == "new_token"
    assert client.refresh_token == "new_refresh"
    mock_post.assert_called_once()


def test_get_headers_include_bearer_token():
    client = StravaClient(
        client_id="123",
        client_secret="secret",
        access_token="mytoken",
        refresh_token="refresh",
    )
    headers = client._headers()
    assert headers["Authorization"] == "Bearer mytoken"
