import json
import os
from pathlib import Path

from voice_suite.google_calendar import CalendarPaths, GoogleCalendarAuth, verify_calendar


class FakeCredentials:
    def __init__(self, *, valid=False, expired=False, refresh_token=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True

    def to_json(self):
        return json.dumps({"saved": True})


def paths(tmp_path: Path) -> CalendarPaths:
    return CalendarPaths(tmp_path / "client_secret.json", tmp_path / "token.json")


def test_diagnose_reports_missing_client_secret_without_exposing_paths(tmp_path):
    diagnosis = GoogleCalendarAuth(paths(tmp_path)).diagnose()
    assert diagnosis.status == "SETUP_REQUIRED"
    assert diagnosis.cause == "client_secret_missing"


def test_recover_refreshes_expired_token_and_secures_saved_file(tmp_path):
    auth_paths = paths(tmp_path)
    auth_paths.client_secret.write_text("{}")
    auth_paths.token.write_text("{}")
    credentials = FakeCredentials(expired=True, refresh_token="present")
    auth = GoogleCalendarAuth(
        auth_paths,
        credentials_loader=lambda *_: credentials,
        request_factory=object,
    )

    diagnosis = auth.recover()

    assert diagnosis.cause == "token_refreshed"
    assert credentials.refreshed
    if os.name != "nt":
        assert auth_paths.token.stat().st_mode & 0o777 == 0o600


def test_recover_runs_installed_app_flow_when_refresh_is_unavailable(tmp_path):
    auth_paths = paths(tmp_path)
    auth_paths.client_secret.write_text("{}")
    auth_paths.token.write_text("{}")
    stale = FakeCredentials()
    fresh = FakeCredentials(valid=True)

    class Flow:
        def run_local_server(self, **kwargs):
            assert kwargs == {"port": 0, "open_browser": False}
            return fresh

    auth = GoogleCalendarAuth(
        auth_paths,
        credentials_loader=lambda *_: stale,
        flow_factory=lambda *_: Flow(),
    )

    assert auth.recover(open_browser=False).cause == "authorization_completed"


def test_recover_reauthorizes_when_google_rejects_refresh_token(tmp_path, monkeypatch):
    auth_paths = paths(tmp_path)
    auth_paths.client_secret.write_text("{}")
    auth_paths.token.write_text("{}")
    stale = FakeCredentials(expired=True, refresh_token="present")
    fresh = FakeCredentials(valid=True)

    class RejectedRefresh(Exception):
        pass

    def reject(_request):
        raise RejectedRefresh

    stale.refresh = reject

    class Flow:
        def run_local_server(self, **kwargs):
            return fresh

    auth = GoogleCalendarAuth(
        auth_paths,
        credentials_loader=lambda *_: stale,
        flow_factory=lambda *_: Flow(),
        request_factory=object,
    )
    monkeypatch.setattr(auth, "_refresh_error_type", lambda: RejectedRefresh)

    assert auth.recover().cause == "authorization_completed"


def test_verify_calendar_performs_read_only_primary_calendar_request():
    class Request:
        def execute(self):
            return {"id": "primary@example.invalid"}

    class Calendars:
        def get(self, **kwargs):
            assert kwargs == {"calendarId": "primary"}
            return Request()

    class Service:
        def calendars(self):
            return Calendars()

    def builder(*args, **kwargs):
        assert args == ("calendar", "v3")
        assert kwargs["cache_discovery"] is False
        return Service()

    assert verify_calendar(object(), service_builder=builder) == "primary@example.invalid"
