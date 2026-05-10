"""
Collect base board games published in 2025–2026 from BGG (no expansions).

Phase 1 — ID collection (Playwright, ~5–10 min):
  Opens a real Chromium browser, paginates through BGG's year-filtered
  advanced search, and caches all game IDs to data/ids_2025_2026.json.
  Subsequent runs reuse the cache and skip this phase.

Phase 2 — Detail fetch (XML API, ~10–20 min):
  Batch-fetches full details (title, publisher, description) via the BGG
  XML API with type=boardgame, which excludes expansions at the source.
  Progress is checkpointed so Ctrl-C / re-run resumes without lost work.

Output: data/games_2025_2026.csv
"""

import os
import sys

from dotenv import load_dotenv

from bgg import scraper, sweep
from bgg.client import BGGClient
from bgg.models import Game

YEAR_MIN = 2025
YEAR_MAX = 2026
YEARS = set(range(YEAR_MIN, YEAR_MAX + 1))


def print_results(games: list[Game]) -> None:
    sep = "-" * 64
    label = f"{YEAR_MIN}–{YEAR_MAX}" if YEAR_MIN != YEAR_MAX else str(YEAR_MIN)
    print(f"\n{sep}")
    print(f"  Base Board Games {label}  —  {len(games)} found")
    print(sep)
    for game in sorted(games, key=lambda g: (g.year, g.name.lower())):
        print()
        print(game.display())
        print(sep)


def main() -> None:
    load_dotenv()
    token = os.getenv("BGG_TOKEN")
    if not token:
        sys.exit(
            "BGG_TOKEN not set. Copy .env.template to .env and add your token."
        )

    # Phase 1: collect game IDs via browser scraping
    years_label = f"{YEAR_MIN}–{YEAR_MAX}"
    print(f"=== Phase 1: collecting {years_label} game IDs via BGG search ===\n")
    ids = scraper.collect_ids(YEAR_MIN, YEAR_MAX)

    if not ids:
        sys.exit("No IDs collected — check the Cloudflare message above.")

    print(f"\n{len(ids):,} IDs ready for detail fetch.\n")

    # Phase 2: fetch full details from the XML API (expansions excluded)
    print(f"=== Phase 2: fetching game details via XML API ===\n")
    client = BGGClient(token)
    games = sweep.run(client, ids, YEARS)

    print_results(games)
    years_str = "_".join(str(y) for y in sorted(YEARS))
    print(f"\nResults saved to data/games_{years_str}.csv")


if __name__ == "__main__":
    main()
