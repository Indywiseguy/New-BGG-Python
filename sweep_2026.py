"""
Sweep the full BGG database for games published in 2026.

Usage:
    python sweep_2026.py [path/to/bg_ranked_items.csv]

If no path is given the script looks for any .csv or .csv.gz file in data/.

The BGG CSV dump must be downloaded manually from:
    https://boardgamegeek.com/data_dumps/bg_ranked_items
(sign in via browser, then download and place it in the data/ folder)

Progress is checkpointed every 50 batches (~1,000 IDs). Ctrl+C saves your
place; re-running resumes from where you stopped.

Results are written to data/games_2026.csv.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from bgg.client import BGGClient
from bgg.models import Game
from bgg import sweep

YEAR = 2026


def find_csv() -> Path:
    data_dir = Path("data")
    for pattern in ("*.csv.gz", "*.csv"):
        candidates = [p for p in data_dir.glob(pattern) if p.name != "games_2026.csv"]
        if candidates:
            return candidates[0]
    sys.exit(
        "No BGG CSV dump found in data/.\n"
        "Download it from: https://boardgamegeek.com/data_dumps/bg_ranked_items\n"
        "Then place it in the data/ folder and re-run."
    )


def print_results(games: list[Game]) -> None:
    sep = "-" * 64
    print(f"\n{sep}")
    print(f"  Board Games Published in {YEAR}  —  {len(games)} found")
    print(sep)
    for game in sorted(games, key=lambda g: g.name.lower()):
        print()
        print(game.display())
        print(sep)


def main() -> None:
    load_dotenv()
    token = os.getenv("BGG_TOKEN")
    if not token:
        sys.exit("Error: BGG_TOKEN not set. Copy .env.template to .env and add your token.")

    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_csv()
    if not csv_path.exists():
        sys.exit(f"File not found: {csv_path}")

    print(f"Loading game IDs from {csv_path}...")
    ids = sweep.load_ids_from_csv(csv_path)

    client = BGGClient(token)
    games = sweep.run(client, ids, YEAR)
    print_results(games)


if __name__ == "__main__":
    main()
