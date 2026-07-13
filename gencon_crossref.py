"""
Cross-reference 2025–2026 BGG games against Gen Con 2026 exhibitors.

Reads:  data/games_2025_2026.csv
Writes: data/games_2025_2026_gencon.csv

Added columns:
  at_gencon        — Yes / No
  gencon_publisher — matched exhibitor name, or N/A
  booth_number     — booth label(s) from the Gen Con list, or N/A

Fuzzy matching is used because publisher names rarely match exactly
(e.g. "Stonemaier" vs "Stonemaier Games").  Adjust MATCH_THRESHOLD
downward if you want more aggressive matching, upward for stricter.
"""

import csv
import sys
from pathlib import Path

from bgg.gencon import best_match, fetch_exhibitors

GAMES_CSV = Path("data/games_2025_2026.csv")
OUTPUT_CSV = Path("data/games_2025_2026_gencon.csv")


def main() -> None:
    if not GAMES_CSV.exists():
        sys.exit(f"Missing {GAMES_CSV} — run sweep_2026.py first.")

    # --- Fetch exhibitors ---
    exhibitors = fetch_exhibitors()
    exhibitor_names = [e["name"] for e in exhibitors]
    booth_by_name = {e["name"]: e["booths"] for e in exhibitors}

    # --- Load games ---
    with open(GAMES_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        games = list(reader)
    print(f"\nLoaded {len(games)} games from {GAMES_CSV}")

    # --- Cross-reference ---
    rows = []
    matched = 0

    for game in games:
        pub_field = game.get("publisher", "")
        name, score = best_match(pub_field, exhibitor_names)

        if name:
            matched += 1
            rows.append(
                {
                    **game,
                    "at_gencon": "Yes",
                    "gencon_publisher": name,
                    "booth_number": booth_by_name[name],
                }
            )
        else:
            rows.append(
                {
                    **game,
                    "at_gencon": "No",
                    "gencon_publisher": "N/A",
                    "booth_number": "N/A",
                }
            )

    # --- Write output ---
    fieldnames = list(games[0].keys()) + ["at_gencon", "gencon_publisher", "booth_number"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"\n{matched} of {len(rows)} games have a publisher attending Gen Con 2026."
    )
    print(f"Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
