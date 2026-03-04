import json
import pytest
from unittest.mock import patch, MagicMock
from src.fetcher import StravaClient


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
