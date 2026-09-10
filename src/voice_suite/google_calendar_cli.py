"""Secret-safe Google Calendar diagnosis, recovery, and verification CLI."""

from __future__ import annotations

import argparse
import json

from .google_calendar import GoogleCalendarAuth, verify_calendar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Google Calendar OAuth maintenance")
    parser.add_argument("action", choices=("diagnose", "recover", "check"))
    parser.add_argument("--no-browser", action="store_true", help="print the authorization URL instead")
    args = parser.parse_args(argv)
    auth = GoogleCalendarAuth()

    if args.action == "diagnose":
        diagnosis = auth.diagnose()
        print(json.dumps(diagnosis.__dict__, ensure_ascii=False))
        return 0 if diagnosis.status == "READY" else 2
    if args.action == "recover":
        diagnosis = auth.recover(open_browser=not args.no_browser)
        print(json.dumps(diagnosis.__dict__, ensure_ascii=False))
        return 0 if diagnosis.status == "READY" else 2

    verify_calendar(auth.credentials())
    print(json.dumps({"status": "READY", "calendar": "primary_verified"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
