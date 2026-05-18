"""
GenCon 2026 Preview — local web app.

Run:  uvicorn webapp:app --reload --port 8000
Open: http://localhost:8000
"""

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_FILE = Path("data/geeklist_user_data.json")
GAMES_CSV  = Path("data/games_2025_2026_gencon.csv")

app = FastAPI(title="GenCon 2026 Preview")

BGG_USERNAME = "indywiseguy"
BGG_PASSWORD = os.environ.get("BGG_PASSWORD", "")

# ---------------------------------------------------------------------------
# BGG collection status helpers
# ---------------------------------------------------------------------------
_STATUS_FIELDS = [
    ("own",         "Own"),
    ("preordered",  "Preordered"),
    ("wanttobuy",   "Want to Buy"),
    ("wishlist",    "Wishlist"),
    ("wanttoplay",  "Want to Play"),
    ("fortrade",    "For Trade"),
    ("prevowned",   "Previously Owned"),
]


def _parse_status(status_el) -> str:
    return ", ".join(label for attr, label in _STATUS_FIELDS if status_el.get(attr) == "1")


def fetch_bgg_collection() -> dict[str, str]:
    """Fetch BGG collection for BGG_USERNAME via authenticated session.

    BGG's XML API returns 401 for private collections when called unauthenticated.
    We log in via Playwright (headed, to pass Cloudflare), grab the session cookies,
    then use those cookies with requests to call the XML API.
    """
    if not BGG_PASSWORD:
        raise HTTPException(status_code=500, detail="BGG_PASSWORD not set in .env")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto("https://boardgamegeek.com/login", wait_until="load")
            page.wait_for_timeout(2000)
            page.fill('input[name="username"]', BGG_USERNAME)
            page.fill('input[name="password"]', BGG_PASSWORD)
            page.click('button:has-text("Sign In")')
            page.wait_for_timeout(6000)
            if "login" in page.url:
                raise HTTPException(status_code=500, detail="BGG login failed — check credentials in .env")
            all_cookies = context.cookies()
        finally:
            browser.close()

    session = requests.Session()
    for c in all_cookies:
        session.cookies.set(c["name"], c["value"])

    url = "https://boardgamegeek.com/xmlapi2/collection"
    params = {
        "username": BGG_USERNAME,
        "subtype": "boardgame",
        "excludesubtype": "boardgameexpansion",
    }
    for attempt in range(8):
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 200:
            break
        if r.status_code == 202:
            time.sleep(5)
        else:
            raise HTTPException(status_code=502, detail=f"BGG returned {r.status_code}")
    else:
        raise HTTPException(status_code=504, detail="BGG collection timed out")

    root = ET.fromstring(r.text)
    result: dict[str, str] = {}
    for item in root.findall("item"):
        oid = item.get("objectid", "")
        status_el = item.find("status")
        result[oid] = _parse_status(status_el) if status_el is not None else ""
    return result


# ---------------------------------------------------------------------------
# Data load / save / init
# ---------------------------------------------------------------------------

def _load() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _init_from_csv() -> None:
    """Build data/geeklist_user_data.json from the CSV if it doesn't exist."""
    import csv as csv_mod

    games: list[dict] = []
    with open(GAMES_CSV, newline="", encoding="utf-8") as fh:
        for row in csv_mod.DictReader(fh):
            if row.get("at_gencon") != "Yes" and row.get("Add to List") != "Yes":
                continue
            games.append({
                "id":               row["id"],
                "name":             row["name"],
                "year":             row["year"],
                "bgg_publisher":    row["publisher"],
                "gencon_publisher": row["gencon_publisher"],
                "booth":            row["booth_number"],
                "bgg_status":       "",
                "interest_level":   "",
                "hot_games_room":   False,
                "rank":             None,
            })

    _save({"games": games, "last_bgg_refresh": None})
    print(f"Initialised {DATA_FILE} with {len(games)} games.")


def _merge_csv_into_existing() -> None:
    """Add any new games from the CSV into an existing data file (preserves user data)."""
    import csv as csv_mod

    data = _load()
    existing_ids = {g["id"] for g in data["games"]}
    added = 0
    with open(GAMES_CSV, newline="", encoding="utf-8") as fh:
        for row in csv_mod.DictReader(fh):
            if row.get("at_gencon") != "Yes" and row.get("Add to List") != "Yes":
                continue
            if row["id"] in existing_ids:
                continue
            data["games"].append({
                "id":               row["id"],
                "name":             row["name"],
                "year":             row["year"],
                "bgg_publisher":    row["publisher"],
                "gencon_publisher": row["gencon_publisher"],
                "booth":            row["booth_number"],
                "bgg_status":       "",
                "interest_level":   "",
                "hot_games_room":   False,
                "rank":             None,
            })
            added += 1
    if added:
        _save(data)
        print(f"Merged {added} new games into {DATA_FILE}.")


# ---------------------------------------------------------------------------
# On startup: ensure data file exists
# ---------------------------------------------------------------------------
@app.on_event("startup")
def startup():
    if not DATA_FILE.exists():
        _init_from_csv()
    else:
        _merge_csv_into_existing()
    # Migrate renamed interest level: "Maybe" → "Likely to Buy"
    data = _load()
    if any(g.get("interest_level") == "Maybe" for g in data["games"]):
        for g in data["games"]:
            if g.get("interest_level") == "Maybe":
                g["interest_level"] = "Likely to Buy"
        _save(data)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/games")
def get_games():
    return _load()["games"]


@app.put("/api/games/{game_id}")
def update_game(game_id: str, body: dict[str, Any]):
    data = _load()
    for game in data["games"]:
        if game["id"] == game_id:
            allowed = {"interest_level", "hot_games_room", "rank"}
            for k, v in body.items():
                if k in allowed:
                    game[k] = bool(v) if k == "hot_games_room" else v
            _save(data)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Game not found")


@app.post("/api/games/bulk-update")
def bulk_update(updates: list[dict[str, Any]]):
    """Update rank (and optionally interest_level) for multiple games at once."""
    data = _load()
    update_map = {u["id"]: u for u in updates}
    allowed = {"interest_level", "hot_games_room", "rank"}
    for game in data["games"]:
        if game["id"] in update_map:
            for k, v in update_map[game["id"]].items():
                if k in allowed:
                    game[k] = v
    _save(data)
    return {"ok": True}


@app.get("/api/bgg/refresh")
def refresh_bgg():
    """Pull the latest BGG collection status for indywiseguy."""
    statuses = fetch_bgg_collection()
    data = _load()
    updated = 0
    for game in data["games"]:
        new_status = statuses.get(game["id"], "")
        if game.get("bgg_status") != new_status:
            game["bgg_status"] = new_status
            updated += 1
    data["last_bgg_refresh"] = time.strftime("%Y-%m-%d %H:%M")
    _save(data)
    return {"ok": True, "updated": updated, "last_refresh": data["last_bgg_refresh"]}


@app.get("/api/meta")
def get_meta():
    data = _load()
    return {"last_bgg_refresh": data.get("last_bgg_refresh"), "total": len(data["games"])}


@app.get("/api/export")
def export_data():
    return FileResponse(
        DATA_FILE,
        media_type="application/json",
        filename="gencon_2026_games.json",
    )


@app.post("/api/import")
async def import_data(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        incoming = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Merge user-editable fields only; keep metadata from CSV
    user_fields = {"interest_level", "hot_games_room", "rank", "bgg_status"}
    if isinstance(incoming, list):
        incoming_map = {g["id"]: g for g in incoming if "id" in g}
    elif isinstance(incoming, dict) and "games" in incoming:
        incoming_map = {g["id"]: g for g in incoming["games"] if "id" in g}
    else:
        raise HTTPException(status_code=400, detail="Expected list or {games:[...]}")

    data = _load()
    merged = 0
    for game in data["games"]:
        if game["id"] in incoming_map:
            src = incoming_map[game["id"]]
            for f in user_fields:
                if f in src:
                    v = src[f]
                    game[f] = bool(v) if f == "hot_games_room" else v
            merged += 1
    _save(data)
    return {"ok": True, "merged": merged}


# ---------------------------------------------------------------------------
# Serve static files (must be last)
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
