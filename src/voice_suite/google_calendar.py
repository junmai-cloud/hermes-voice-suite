"""Google Calendar OAuth and read-only health checks.

OAuth material stays outside the repository.  Google imports are deliberately
lazy so the dependency-light core and its tests do not require the SDK.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


READ_ONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


@dataclass(frozen=True)
class CalendarPaths:
    client_secret: Path
    token: Path

    @classmethod
    def defaults(cls, home: Path | None = None) -> "CalendarPaths":
        root = (home or Path.home()) / ".config" / "hermes-voice-suite" / "google-calendar"
        return cls(root / "client_secret.json", root / "token.json")


@dataclass(frozen=True)
class CalendarDiagnosis:
    status: str
    cause: str
    next_action: str


class GoogleCalendarAuth:
    """Own the installed-app OAuth lifecycle without logging credential data."""

    def __init__(
        self,
        paths: CalendarPaths | None = None,
        *,
        credentials_loader: Callable[..., Any] | None = None,
        flow_factory: Callable[..., Any] | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.paths = paths or CalendarPaths.defaults()
        self._credentials_loader = credentials_loader
        self._flow_factory = flow_factory
        self._request_factory = request_factory

    def diagnose(self) -> CalendarDiagnosis:
        if not self.paths.client_secret.is_file():
            return CalendarDiagnosis("SETUP_REQUIRED", "client_secret_missing", "install_client_secret")
        if not self.paths.token.is_file():
            return CalendarDiagnosis("AUTH_REQUIRED", "token_missing", "authorize")
        try:
            credentials = self._load_credentials()
        except (OSError, ValueError, TypeError):
            return CalendarDiagnosis("AUTH_REQUIRED", "token_invalid", "authorize")
        if getattr(credentials, "valid", False):
            return CalendarDiagnosis("READY", "credentials_valid", "check_calendar")
        if getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None):
            return CalendarDiagnosis("REFRESH_AVAILABLE", "access_token_expired", "refresh")
        return CalendarDiagnosis("AUTH_REQUIRED", "refresh_unavailable", "authorize")

    def recover(self, *, open_browser: bool = True) -> CalendarDiagnosis:
        diagnosis = self.diagnose()
        if diagnosis.status == "READY":
            return diagnosis
        if diagnosis.status == "REFRESH_AVAILABLE":
            credentials = self._load_credentials()
            try:
                credentials.refresh(self._request())
            except self._refresh_error_type():
                diagnosis = CalendarDiagnosis("AUTH_REQUIRED", "refresh_rejected", "authorize")
            else:
                self._save(credentials)
                return CalendarDiagnosis("READY", "token_refreshed", "check_calendar")
        if diagnosis.cause == "client_secret_missing":
            return diagnosis

        flow = self._flow()
        credentials = flow.run_local_server(port=0, open_browser=open_browser)
        self._save(credentials)
        return CalendarDiagnosis("READY", "authorization_completed", "check_calendar")

    def credentials(self) -> Any:
        diagnosis = self.recover()
        if diagnosis.status != "READY":
            raise RuntimeError(diagnosis.cause)
        return self._load_credentials()

    def _load_credentials(self) -> Any:
        loader = self._credentials_loader
        if loader is None:
            try:
                from google.oauth2.credentials import Credentials
            except ImportError as exc:
                raise RuntimeError("Install the 'calendar' optional dependency") from exc
            loader = Credentials.from_authorized_user_file
        return loader(str(self.paths.token), [READ_ONLY_SCOPE])

    def _flow(self) -> Any:
        factory = self._flow_factory
        if factory is None:
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
            except ImportError as exc:
                raise RuntimeError("Install the 'calendar' optional dependency") from exc
            factory = InstalledAppFlow.from_client_secrets_file
        return factory(str(self.paths.client_secret), [READ_ONLY_SCOPE])

    def _request(self) -> Any:
        if self._request_factory is not None:
            return self._request_factory()
        try:
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise RuntimeError("Install the 'calendar' optional dependency") from exc
        return Request()

    @staticmethod
    def _refresh_error_type() -> type[Exception]:
        try:
            from google.auth.exceptions import RefreshError
        except ImportError:
            return RuntimeError
        return RefreshError

    def _save(self, credentials: Any) -> None:
        self.paths.token.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.paths.token.name}.",
            suffix=".tmp",
            dir=self.paths.token.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(credentials.to_json())
            _restrict_file(temporary_path)
            os.replace(temporary_path, self.paths.token)
        finally:
            temporary_path.unlink(missing_ok=True)


def _restrict_file(path: Path) -> None:
    """Restrict an OAuth file to its owner on POSIX and Windows."""

    path.chmod(0o600)
    if os.name != "nt":
        return

    username = getpass.getuser()
    domain = os.environ.get("USERDOMAIN", "").strip()
    account = f"{domain}\\{username}" if domain else username
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:F"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Unable to secure the Google Calendar OAuth file") from exc


def verify_calendar(credentials: Any, *, service_builder: Callable[..., Any] | None = None) -> str:
    """Perform the smallest useful API read and return the primary calendar ID."""
    builder = service_builder
    if builder is None:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Install the 'calendar' optional dependency") from exc
        builder = build
    service = builder("calendar", "v3", credentials=credentials, cache_discovery=False)
    result = service.calendars().get(calendarId="primary").execute()
    return str(result["id"])
