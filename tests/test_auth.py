import os
import tempfile
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
