#!/usr/bin/env python3
"""
Scheduled (launchd) trigger for the "Refresh Preview List" action — pulls the
public GenCon 2026 GeekPreview catalog into Supabase. No BGG login involved,
so this is safe to run unattended on a schedule (see webapp.py:refresh_preview
for the actual logic, reused here as-is).

Self-expires: once run past END_DATE, it unloads its own launchd job and
deletes the plist so it stops firing without needing to remember to disable
it manually. See launchd/com.indywiseguy.gencon-preview-refresh.plist for the
schedule (midnight/noon/4pm/8pm US Eastern, daily).
"""

import os
import subprocess
from datetime import date
from pathlib import Path

END_DATE = date(2026, 8, 5)
PLIST_LABEL = "com.indywiseguy.gencon-preview-refresh"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _log(msg: str) -> None:
    print(f"[{date.today().isoformat()}] {msg}", flush=True)


def _self_expire() -> None:
    _log(f"Past end date {END_DATE.isoformat()} — unloading scheduled job and removing plist.")
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{PLIST_LABEL}"],
        capture_output=True,
    )
    PLIST_PATH.unlink(missing_ok=True)


def main() -> None:
    if date.today() > END_DATE:
        _self_expire()
        return

    from webapp import refresh_preview

    try:
        result = refresh_preview()
        _log(f"OK: {result}")
    except Exception as exc:
        _log(f"FAILED: {exc}")
        raise


if __name__ == "__main__":
    main()
