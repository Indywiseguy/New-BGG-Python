"""
Mine BGG for board games published in 2026.

Strategy: BGG's search API has no year filter, so we cast a wide net by
running many broad-term searches + the hot list, deduplicate the resulting
IDs, batch-fetch full /thing details, then keep only year == 2026.

This covers the majority of notable 2026 releases. For an exhaustive list
you would additionally need to walk a range of recent BGG item IDs.
"""

import os
import sys

from dotenv import load_dotenv

from bgg.client import BGGClient, BGGError
from bgg.models import Game

YEAR = 2026

# Wide vocabulary; more terms = better coverage at the cost of more API calls.
SEARCH_TERMS = [
    "quest", "adventure", "war", "city", "realm", "dragon", "castle",
    "empire", "dungeon", "space", "magic", "strategy", "card", "dice",
    "tower", "kingdom", "world", "saga", "legacy", "deckbuilding",
    "cooperative", "fantasy", "pirate", "zombie", "mystery", "heist",
    "train", "engine", "euro", "worker", "placement", "area", "control",
    "the", "of", "age", "rise", "fall", "last", "lost", "dark", "light",
    "island", "sea", "forest", "iron", "stone", "gold", "shadow", "fire",
]


def collect_ids(client: BGGClient) -> set[int]:
    ids: set[int] = set()

    print("→ Fetching hot list...")
    hot = client.get_hot()
    ids.update(hot)
    print(f"  {len(hot)} IDs from hot list  (total unique: {len(ids)})")

    for term in SEARCH_TERMS:
        print(f"→ Searching '{term}'...", end=" ", flush=True)
        found = client.search(term)
        before = len(ids)
        ids.update(found)
        print(f"{len(found)} results, {len(ids) - before} new  (total: {len(ids)})")

    return ids


def fetch_2026_games(client: BGGClient, ids: set[int]) -> list[Game]:
    id_list = list(ids)
    batch_size = 20
    total_batches = (len(id_list) + batch_size - 1) // batch_size
    games: list[Game] = []

    print(f"\n→ Fetching details for {len(id_list)} games in {total_batches} batches...")
    for i in range(0, len(id_list), batch_size):
        batch = id_list[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Batch {batch_num}/{total_batches}...", end=" ", flush=True)
        things = client.get_things(batch)
        hits = [Game(**t) for t in things if t["year"] == YEAR]
        games.extend(hits)
        print(f"{len(hits)} from {YEAR}" if hits else "none")

    return games


def print_results(games: list[Game]) -> None:
    separator = "─" * 64
    print(f"\n{separator}")
    print(f"  Board Games Published in {YEAR}  —  {len(games)} found")
    print(separator)

    if not games:
        print("\n  No games found. Try expanding SEARCH_TERMS or checking your token.")
        return

    for game in sorted(games, key=lambda g: g.name.lower()):
        print()
        print(game.display())
        print(separator)


def main() -> None:
    load_dotenv()
    token = os.getenv("BGG_TOKEN")
    if not token:
        sys.exit("Error: BGG_TOKEN is not set. Copy .env.template to .env and add your token.")

    client = BGGClient(token)

    try:
        ids = collect_ids(client)
        games = fetch_2026_games(client, ids)
        print_results(games)
    except BGGError as exc:
        sys.exit(f"BGG API error: {exc}")


if __name__ == "__main__":
    main()
