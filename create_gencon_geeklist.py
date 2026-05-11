"""
Create "Vinny's GenCon 2026 Preview List" on BGG.

Reads  data/games_2025_2026_gencon.csv
Adds   all rows where at_gencon == 'Yes'
Each item's body: "Publisher: <gencon_publisher> | Booth: <booth_number>"

Writes a checkpoint file (data/geeklist_checkpoint.json) so the run can be
resumed if interrupted — just re-run the script.
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from bgg.geeklist import login_and_get_token, create_geeklist, add_item

load_dotenv(Path(__file__).parent / ".env")

USERNAME   = "indywiseguy"
PASSWORD   = os.environ["BGG_PASSWORD"]

GAMES_CSV  = Path("data/games_2025_2026_gencon.csv")
CHECKPOINT = Path("data/geeklist_checkpoint.json")
LIST_NAME  = "Vinny's GenCon 2026 Preview List"
LIST_DESC  = (
    "Board games published in 2025–2026 by publishers attending Gen Con 2026, "
    "automatically cross-referenced from BGG data."
)
ITEM_DELAY = 0.75   # seconds between additions (857 items ≈ 11 min)


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {"geeklist_id": None, "added": []}


def save_checkpoint(cp: dict) -> None:
    CHECKPOINT.write_text(json.dumps(cp, indent=2))


def load_games() -> list[dict]:
    with open(GAMES_CSV, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("at_gencon") == "Yes"]


def main() -> None:
    if not GAMES_CSV.exists():
        sys.exit(f"Missing {GAMES_CSV} — run sweep_2026.py and gencon_crossref.py first.")

    games = load_games()
    print(f"Loaded {len(games)} games flagged at_gencon=Yes")

    cp = load_checkpoint()

    # --- Get auth token via Playwright browser ---
    print("\nOpening browser to authenticate...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context()
        page = ctx.new_page()

        auth_token = login_and_get_token(page, USERNAME, PASSWORD)
        browser.close()

    print("Browser closed. Using API token for remaining calls.\n")

    # --- Create geeklist if not already done ---
    if cp["geeklist_id"] is None:
        gl_id = create_geeklist(auth_token, LIST_NAME, LIST_DESC, private=True)
        cp["geeklist_id"] = gl_id
        save_checkpoint(cp)
    else:
        gl_id = cp["geeklist_id"]
        print(f"Resuming — using existing geeklist id={gl_id}")

    already_added = set(cp["added"])
    remaining = [g for g in games if g["id"] not in already_added]
    print(f"{len(already_added)} already added, {len(remaining)} remaining\n")

    # --- Add items ---
    success = 0
    fail    = 0

    for i, game in enumerate(remaining, start=len(already_added) + 1):
        game_id = game["id"]
        title   = game.get("name", "?")
        pub     = game.get("gencon_publisher", "N/A")
        booth   = game.get("booth_number", "N/A")
        body    = f"Publisher: {pub} | Booth: {booth}"

        print(f"  [{i}/{len(games)}] {title} (id={game_id})")

        item_id = add_item(auth_token, gl_id, int(game_id), body, index=i)

        if item_id:
            success += 1
            cp["added"].append(game_id)   # game_id is the csv "id" field (string)
            if success % 25 == 0:
                save_checkpoint(cp)
        else:
            fail += 1

        time.sleep(ITEM_DELAY)

    save_checkpoint(cp)

    print(f"\nDone. {success} added, {fail} failed.")
    print(f"Geeklist: https://boardgamegeek.com/geeklist/{gl_id}")


if __name__ == "__main__":
    main()
