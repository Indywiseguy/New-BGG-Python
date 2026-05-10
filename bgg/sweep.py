import csv
import gzip
import json
import sys
from pathlib import Path

from .client import BGGClient
from .models import Game

DATA_DIR = Path("data")
CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"
RESULTS_FILE = DATA_DIR / "games_2026.csv"

# BGG CSV dumps use one of these column names for the game ID
_ID_COLUMNS = ("objectid", "id", "game_id", "gameid")
_BATCH_SIZE = 20
_SAVE_EVERY = 50  # batches between checkpoint writes


def load_ids_from_csv(csv_path: Path) -> list[int]:
    opener = gzip.open if csv_path.suffix == ".gz" else open
    with opener(csv_path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = [h.lower().strip() for h in (reader.fieldnames or [])]

        id_col = next((c for c in _ID_COLUMNS if c in headers), None)
        if id_col is None:
            sys.exit(
                f"Could not find a game-ID column in {csv_path}.\n"
                f"Columns found: {headers}\n"
                f"Expected one of: {_ID_COLUMNS}"
            )

        ids = []
        for row in reader:
            raw = row.get(id_col) or row.get(id_col.capitalize(), "")
            try:
                ids.append(int(raw.strip()))
            except ValueError:
                pass

    ids.sort()
    print(f"  {len(ids):,} game IDs loaded from {csv_path}")
    return ids


def _load_checkpoint() -> tuple[int, list[dict]]:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        offset = data.get("offset", 0)
        games = data.get("games", [])
        print(
            f"Resuming from checkpoint: "
            f"{offset:,} IDs processed, {len(games)} games found so far"
        )
        return offset, games
    return 0, []


def _save_checkpoint(offset: int, games: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps({"offset": offset, "games": games}))


def _save_results_csv(games: list[dict]) -> None:
    if not games:
        return
    DATA_DIR.mkdir(exist_ok=True)
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["id", "name", "publisher", "year", "description"]
        )
        writer.writeheader()
        for g in sorted(games, key=lambda x: x["name"].lower()):
            writer.writerow(
                {
                    "id": g["id"],
                    "name": g["name"],
                    "publisher": "; ".join(g["publishers"]),
                    "year": g["year"],
                    "description": g["description"],
                }
            )


def run(client: BGGClient, ids: list[int], year: int) -> list[Game]:
    total = len(ids)
    total_batches = (total + _BATCH_SIZE - 1) // _BATCH_SIZE
    offset, found = _load_checkpoint()

    eta_min = (total - offset) * 2 / _BATCH_SIZE / 60
    print(f"Sweeping {total:,} games ({total_batches:,} batches) — est. {eta_min:.0f} min")
    print("Press Ctrl+C at any time to pause; re-run to resume.\n")

    try:
        for i in range(offset, total, _BATCH_SIZE):
            batch_num = i // _BATCH_SIZE + 1
            pct = i / total * 100
            print(
                f"\r  [{pct:5.1f}%] batch {batch_num:,}/{total_batches:,} "
                f"| found {len(found)}",
                end="",
                flush=True,
            )

            things = client.get_things(ids[i : i + _BATCH_SIZE])
            for t in things:
                if t["year"] == year:
                    found.append(t)
                    print(
                        f"\n  + {t['name']} ({'; '.join(t['publishers']) or 'Unknown'})",
                        flush=True,
                    )

            if batch_num % _SAVE_EVERY == 0:
                _save_checkpoint(i + _BATCH_SIZE, found)
                _save_results_csv(found)

    except KeyboardInterrupt:
        print("\n\nPaused — saving checkpoint...", flush=True)
        _save_checkpoint(i, found)
        _save_results_csv(found)
        print(f"Progress saved. Run again to resume from batch {i // _BATCH_SIZE + 1:,}.")
        sys.exit(0)

    # Completed
    _save_checkpoint(total, found)
    _save_results_csv(found)
    print(f"\n\nDone. {len(found)} games found.")
    return [Game(**g) for g in found]
