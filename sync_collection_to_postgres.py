"""
Pull my full BGG collection (including private comments / inventory fields)
and load it into a table in my self-hosted Postgres database.

Reuses export_collection.fetch_collection_rows() for the actual BGG fetch
(native CSV export via a headed-browser login + the supplemental XML API
call), then upserts the result into Postgres via bgg.postgres_sync.

Requires in .env:
    BGG_PASSWORD    - your BGG account password (BGG_USERNAME defaults to "indywiseguy")
    POSTGRES_DSN    - e.g. postgresql://user:password@host:5432/dbname
    POSTGRES_TABLE  - optional, defaults to "bgg_collection"

Usage:
    python sync_collection_to_postgres.py
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bgg.postgres_sync import sync_to_postgres, table_name  # noqa: E402
from export_collection import fetch_collection_rows  # noqa: E402


def main() -> None:
    print("Fetching BGG collection...", flush=True)
    rows = fetch_collection_rows()
    print(f"Fetched {len(rows)} collection items.", flush=True)

    print(f"Syncing to Postgres table '{table_name()}'...", flush=True)
    written = sync_to_postgres(rows)
    print(f"Done. Upserted {written} rows.", flush=True)


if __name__ == "__main__":
    main()
