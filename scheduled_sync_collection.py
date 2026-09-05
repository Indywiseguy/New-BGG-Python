#!/usr/bin/env python3
"""
Scheduled (launchd) trigger for sync_collection_to_postgres.py — pulls the
full BGG collection (private fields included) and upserts it into Postgres.

This does a real headed-browser login (Playwright, headless=False) to get
BGG's native CSV export, so it needs to run in a logged-in GUI session — see
launchd/com.indywiseguy.bgg-collection-postgres-sync.plist, which loads it as
a per-user (gui/<uid>) LaunchAgent, same as the other scheduled jobs in this
repo. Expect a visible Chromium window to pop up briefly on each run.
"""

from datetime import date

from sync_collection_to_postgres import main as sync_main


def _log(msg: str) -> None:
    print(f"[{date.today().isoformat()}] {msg}", flush=True)


def main() -> None:
    try:
        sync_main()
        _log("OK")
    except Exception as exc:
        _log(f"FAILED: {exc}")
        raise


if __name__ == "__main__":
    main()
