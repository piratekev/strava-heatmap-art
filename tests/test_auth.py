import os
import tempfile
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse
from unittest.mock import MagicMock
import pytest


def test_check_env_credentials_raises_if_missing(monkeypatch):
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    from auth import _check_env_credentials
    with pytest.raises(SystemExit):
        _check_env_credentials()


def test_check_env_credentials_passes_when_set(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "abc")
    from auth import _check_env_credentials
    _check_env_credentials()  # should not raise


def test_upsert_env_tokens_updates_existing_keys():
    """Updates ACCESS_TOKEN and REFRESH_TOKEN lines that already exist."""
    from auth import _upsert_env_tokens
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("STRAVA_CLIENT_ID=123\n")
        f.write("STRAVA_ACCESS_TOKEN=old_access\n")
        f.write("STRAVA_REFRESH_TOKEN=old_refresh\n")
        path = f.name
    try:
        _upsert_env_tokens(path, "new_access", "new_refresh")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=new_access" in content
        assert "STRAVA_REFRESH_TOKEN=new_refresh" in content
        assert "STRAVA_CLIENT_ID=123" in content
        assert "old_access" not in content
        assert "old_refresh" not in content
    finally:
        os.unlink(path)


def test_check_env_credentials_raises_if_only_one_missing(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    from auth import _check_env_credentials
    with pytest.raises(SystemExit):
        _check_env_credentials()


def test_upsert_env_tokens_appends_missing_keys():
    """Appends ACCESS_TOKEN and REFRESH_TOKEN if not already in .env."""
    from auth import _upsert_env_tokens
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("STRAVA_CLIENT_ID=123\n")
        path = f.name
    try:
        _upsert_env_tokens(path, "new_access", "new_refresh")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=new_access" in content
        assert "STRAVA_REFRESH_TOKEN=new_refresh" in content
    finally:
        os.unlink(path)


def test_upsert_env_tokens_creates_env_if_missing():
    """Creates .env from scratch if it doesn't exist."""
    from auth import _upsert_env_tokens
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".env")
        _upsert_env_tokens(path, "acc", "ref")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=acc" in content
        assert "STRAVA_REFRESH_TOKEN=ref" in content


@pytest.mark.parametrize("ending", ["", "\n"])
@pytest.mark.parametrize("existing_token", ["", "\nSTRAVA_REFRESH_TOKEN=old"])
def test_upsert_env_tokens_preserves_last_line(tmp_path, ending, existing_token):
    from auth import _upsert_env_tokens
    from dotenv import dotenv_values
    path = tmp_path / ".env"
    path.write_text("STRAVA_CLIENT_SECRET=fake_secret" + existing_token + ending)
    _upsert_env_tokens(path, "fake_access", "fake_refresh")
    values = dotenv_values(path)
    assert values["STRAVA_CLIENT_SECRET"] == "fake_secret"
    assert values["STRAVA_ACCESS_TOKEN"] == "fake_access"
    assert values["STRAVA_REFRESH_TOKEN"] == "fake_refresh"


def _callback(server, **params):
    from auth import CallbackHandler
    handler = CallbackHandler.__new__(CallbackHandler)
    handler.server = server
    handler.path = "/?" + urlencode(params)
    handler.wfile = BytesIO()
    handler.send_response = MagicMock()
    handler.end_headers = MagicMock()
    handler.do_GET()
    return handler


@pytest.mark.parametrize("state", [None, "", "wrong-flow", "wrong-\N{SNOWMAN}"])
def test_callback_rejects_missing_or_mismatched_state(state):
    server = SimpleNamespace(oauth_state="current-flow", auth_code=None, auth_error=None)
    params = {"code": "untrusted-code"}
    if state is not None:
        params["state"] = state
    handler = _callback(server, **params)
    handler.send_response.assert_called_once_with(400)
    assert server.auth_code is None
    assert server.auth_error is None


def test_callback_accepts_only_the_current_flow():
    server = SimpleNamespace(oauth_state="current-flow", auth_code=None, auth_error=None)
    _callback(server, code="untrusted-code", state="wrong-flow")
    handler = _callback(server, code="valid-code", state="current-flow")
    handler.send_response.assert_called_once_with(200)
    assert server.auth_code == "valid-code"


def test_callback_records_declined_authorization():
    server = SimpleNamespace(oauth_state="current-flow", auth_code=None, auth_error=None)
    _callback(server, error="access_denied", state="current-flow")
    assert server.auth_error == "access_denied"
    assert server.auth_code is None


def test_auth_main_generates_fresh_state_and_closes_server(monkeypatch, tmp_path):
    import auth
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-client")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-secret")
    servers = []
    urls = []

    def create_server(*args):
        server = MagicMock()
        server.__enter__.return_value = server
        server.handle_request.side_effect = lambda: _callback(
            server, code="valid-code", state=server.oauth_state)
        servers.append(server)
        return server

    monkeypatch.setattr(auth, "HTTPServer", create_server)
    monkeypatch.setattr(auth.webbrowser, "open", urls.append)
    response = MagicMock()
    response.json.return_value = {
        "access_token": "fake-access", "refresh_token": "fake-refresh",
        "athlete": {"firstname": "Test", "lastname": "Runner"},
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr(auth.requests, "post", post)
    auth.main()
    auth.main()
    states = [parse_qs(urlparse(url).query)["state"][0] for url in urls]
    assert states[0] != states[1]
    assert all(len(state) >= 32 for state in states)
    for server, state in zip(servers, states):
        assert server.oauth_state == state
        server.__exit__.assert_called_once()
    assert all(call.kwargs["data"]["code"] == "valid-code" for call in post.call_args_list)
    assert "STRAVA_ACCESS_TOKEN=fake-access\n" in (tmp_path / ".env").read_text()


def test_auth_main_times_out_and_closes_server(monkeypatch):
    import auth
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-client")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-secret")
    server = MagicMock()
    server.__enter__.return_value = server
    monkeypatch.setattr(auth, "HTTPServer", MagicMock(return_value=server))
    monkeypatch.setattr(auth.webbrowser, "open", MagicMock())
    monkeypatch.setattr(auth.time, "monotonic", MagicMock(side_effect=[0, 301]))
    with pytest.raises(SystemExit, match="timed out"):
        auth.main()
    server.__exit__.assert_called_once()
