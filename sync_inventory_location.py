"""
Extract [1-5]-Label tags (Permanent/Resident/Transient/Evaluate/Exiting) from
the Private Comments of Owned games and move them into Inventory Location.

Pipeline (see CLAUDE-facing proposal for full rationale):
  1. backup   - snapshot current private_comment/inv_location for all Owned games
  2. dry-run  - regex-extract tags, write a before/after preview CSV, write NOTHING to BGG
  3. live     - actually apply the change on boardgamegeek.com via browser automation
                (--limit N to do a test batch, --ids to target specific game ids)

Usage:
    python sync_inventory_location.py backup
    python sync_inventory_location.py dry-run
    python sync_inventory_location.py live --limit 10
    python sync_inventory_location.py live --ids 174430,161936
    python sync_inventory_location.py live              # full run (all remaining matches)

Requires data/bgg_collection.csv (from export_collection.py) as the source of
truth for which games are Owned and what their current Private Comments /
Inventory Location values are.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Windows console defaults to cp1252, which chokes on stray unicode in some
# game titles/comments (mis-encoded em dashes etc.). Force UTF-8 output.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SOURCE_CSV   = Path("data/bgg_collection.csv")
BACKUP_DIR   = Path("data/inv_location_backups")
DRYRUN_OUT   = Path("data/inv_location_dry_run.csv")
CHECKPOINT   = Path("data/inv_location_checkpoint.json")

BGG_USERNAME = os.environ.get("BGG_USERNAME", "indywiseguy")
BGG_PASSWORD = os.environ.get("BGG_PASSWORD")

COLLECTION_URL = f"https://boardgamegeek.com/collection/user/{BGG_USERNAME}?subtype=boardgame&own=1"
NUM_PAGES = 3  # 636 owned / 300 per page as of Aug 2026; re-check if collection grows past 900

TAG_PATTERN = re.compile(
    r"\[\s*([1-5])\s*-\s*(Permanent|Resident|Transient|Evaluate|Exiting)\s*\]",
    re.IGNORECASE,
)


def extract_and_strip(comment: str) -> tuple[str | None, str]:
    """
    Find the first [N-Label] tag in *comment*.
    Returns (new_inv_location_value_or_None, comment_with_tag_removed_and_cleaned).
    If no tag is found, returns (None, comment) unchanged.
    """
    match = TAG_PATTERN.search(comment)
    if not match:
        return None, comment

    num, label = match.group(1), match.group(2)
    # Normalize label capitalization (e.g. "resident" -> "Resident")
    label = label.capitalize()
    new_location = f"{num}-{label}"

    stripped = comment[: match.start()] + comment[match.end():]
    # Clean up whitespace left behind: collapse the now-empty/blank first
    # line and any leading blank lines, but preserve the rest as-is.
    stripped = re.sub(r"^[ \t]*\n", "", stripped)   # drop empty first line
    stripped = stripped.strip()

    return new_location, stripped


def load_owned_rows(csv_path: Path = SOURCE_CSV) -> list[dict]:
    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if r.get("own") == "1"]


def build_plan(csv_path: Path = SOURCE_CSV) -> list[dict]:
    """Returns one dict per Owned game that has a matching tag, describing the change."""
    plan = []
    for row in load_owned_rows(csv_path):
        old_comment = row.get("private_comment", "") or ""
        new_location, new_comment = extract_and_strip(old_comment)
        if new_location is None:
            continue
        plan.append({
            "id": row["id"],
            "collid": row["collid"],
            "name": row["name"],
            "old_private_comment": old_comment,
            "new_private_comment": new_comment,
            "old_inv_location": row.get("inv_location", "") or "",
            "new_inv_location": new_location,
            "overwrites_existing_location": bool((row.get("inv_location") or "").strip()),
        })
    return plan


def cmd_backup(args):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = BACKUP_DIR / f"owned_snapshot_{ts}.csv"
    owned = load_owned_rows()
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "collid", "name", "private_comment", "inv_location"])
        writer.writeheader()
        for r in owned:
            writer.writerow({
                "id": r["id"],
                "collid": r["collid"],
                "name": r["name"],
                "private_comment": r.get("private_comment", ""),
                "inv_location": r.get("inv_location", ""),
            })
    print(f"Backed up {len(owned)} owned games to {out_path}")


def cmd_dry_run(args):
    plan = build_plan()
    DRYRUN_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(DRYRUN_OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "id", "collid", "name",
            "old_inv_location", "new_inv_location", "overwrites_existing_location",
            "old_private_comment", "new_private_comment",
        ])
        writer.writeheader()
        writer.writerows(plan)

    overwrites = sum(1 for p in plan if p["overwrites_existing_location"])
    print(f"Dry run: {len(plan)} games would change.")
    print(f"  -> {overwrites} of those would overwrite an existing Inventory Location value.")
    print(f"Full preview written to {DRYRUN_OUT}")
    print()
    print("First 5 planned changes:")
    for p in plan[:5]:
        print(f"  [{p['id']}] {p['name']}")
        print(f"      inv_location: {p['old_inv_location']!r} -> {p['new_inv_location']!r}")
        print(f"      private_comment: {p['old_private_comment']!r} -> {p['new_private_comment']!r}")


def _load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {}


def _save_checkpoint(state: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _login(page, username: str, password: str) -> None:
    page.goto("https://boardgamegeek.com/login", wait_until="load")
    page.wait_for_timeout(2000)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button:has-text("Sign In")')
    page.wait_for_timeout(6000)
    if "login" in page.url:
        raise RuntimeError("BGG login failed -- check credentials in .env")


def _enable_ownership_column(page) -> None:
    page.goto(COLLECTION_URL, wait_until="load")
    page.wait_for_timeout(3000)
    page.click("text=Columns »")
    page.wait_for_timeout(800)
    if not page.is_checked("#columns_ownership"):
        page.check("#columns_ownership")
    page.click("input[value='Done']")
    page.wait_for_timeout(4000)


def _collids_on_current_page(page) -> set[str]:
    html = page.content()
    return set(re.findall(r"collid:\s*'(\d+)'", html))


def _edit_one(page, collid: str, new_comment: str, new_location: str, log) -> bool:
    """Open the Private Info modal for *collid* on the currently-loaded page,
    set privatecomment/invlocation, click Save, and confirm the modal closed."""
    cell = page.query_selector(f"td.editfield[onclick*='{collid}'][onclick*='ownership']")
    if cell is None:
        log(f"  [{collid}] not found on this page")
        return False

    try:
        cell.click()
        page.wait_for_selector("#legacy_modal textarea[name='privatecomment']", timeout=10000)

        page.fill("#legacy_modal textarea[name='privatecomment']", new_comment)
        page.fill("#legacy_modal input[name='invlocation']", new_location)
        page.click("#legacy_modal input[type='submit'][value='Save']")

        # CE_SaveData clears #legacy_modal's innerHTML on completion
        page.wait_for_function(
            "document.getElementById('legacy_modal').innerHTML.trim() === ''",
            timeout=15000,
        )
    except Exception as e:
        log(f"  [{collid}] error during edit: {type(e).__name__}: {e}")
        return False

    return True


def cmd_live(args):
    if not BGG_PASSWORD:
        raise SystemExit("BGG_PASSWORD not set in .env")

    plan = build_plan()
    checkpoint = _load_checkpoint()

    if args.ids:
        wanted_ids = {s.strip() for s in args.ids.split(",")}
        plan = [p for p in plan if p["id"] in wanted_ids]
    plan = [p for p in plan if checkpoint.get(p["id"], {}).get("status") != "done"]
    if args.limit:
        plan = plan[: args.limit]

    if not plan:
        print("Nothing to do (no matching, not-yet-done items).")
        return

    print(f"About to LIVE-EDIT {len(plan)} game(s) on boardgamegeek.com:", flush=True)
    for p in plan:
        print(f"  [{p['id']}] {p['name']}: inv_location {p['old_inv_location']!r} -> {p['new_inv_location']!r}", flush=True)
    if args.yes:
        print(f"\n--yes passed, proceeding with {len(plan)} change(s) without prompting.", flush=True)
    else:
        confirm = input(f"\nType YES to write these {len(plan)} change(s) to BGG: ")
        if confirm.strip() != "YES":
            print("Aborted, nothing written.")
            return

    by_collid = {p["collid"]: p for p in plan}
    remaining = set(by_collid.keys())

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("Logging in...", flush=True)
        _login(page, BGG_USERNAME, BGG_PASSWORD)
        print("Enabling Private Info column...", flush=True)
        _enable_ownership_column(page)

        def _log(msg):
            print(msg, flush=True)

        for pg in range(1, NUM_PAGES + 1):
            if not remaining:
                break
            page.evaluate(f"CE_SetPage({pg})")
            page.wait_for_timeout(3000)
            page_collids = _collids_on_current_page(page) & remaining
            if not page_collids:
                continue
            print(f"Page {pg}: {len(page_collids)} target item(s) found.", flush=True)
            for collid in list(page_collids):
                p = by_collid[collid]
                ok = _edit_one(page, collid, p["new_private_comment"], p["new_inv_location"], _log)
                status = "done" if ok else "failed"
                checkpoint[p["id"]] = {
                    "status": status,
                    "name": p["name"],
                    "new_inv_location": p["new_inv_location"],
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
                _save_checkpoint(checkpoint)
                print(f"  [{p['id']}] {p['name']}: {status}", flush=True)
                remaining.discard(collid)
                time.sleep(1.5)  # be polite

        browser.close()

    if remaining:
        missing = [by_collid[c]["name"] for c in remaining]
        print(f"\n{len(remaining)} item(s) were not found on any of {NUM_PAGES} pages (collection may have grown): {missing}")

    done = sum(1 for v in checkpoint.values() if v["status"] == "done")
    failed = sum(1 for v in checkpoint.values() if v["status"] == "failed")
    print(f"\nCheckpoint totals: {done} done, {failed} failed. See {CHECKPOINT}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("backup", help="Snapshot current Owned games' private_comment/inv_location")
    sub.add_parser("dry-run", help="Preview extraction/removal without writing to BGG")

    live_p = sub.add_parser("live", help="Apply changes to boardgamegeek.com")
    live_p.add_argument("--limit", type=int, default=None, help="Only process the first N matches")
    live_p.add_argument("--ids", type=str, default=None, help="Comma-separated BGG game ids to restrict to")
    live_p.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt (for non-interactive/background runs)")

    args = parser.parse_args()
    {"backup": cmd_backup, "dry-run": cmd_dry_run, "live": cmd_live}[args.command](args)


if __name__ == "__main__":
    main()
