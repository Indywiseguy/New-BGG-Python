"""
GenCon 2026 Preview — local refresh server.

Browsing/editing lives in static/ and talks directly to Supabase (project
"boardgames") — see static/app.js. It's deployed as a static site to Netlify.

This local server only exists for the two actions that can't run in the
cloud: pulling BGG's official GeekPreview list #92
(https://boardgamegeek.com/geekpreview/92/gen-con-2026-preview), and logging
into BGG (via a real, visible browser — Cloudflare blocks headless logins)
to pull personal priority/collection data. Both write straight into the same
Supabase tables the deployed site reads from.

Run:  uvicorn webapp:app --reload --port 8000
Open: http://localhost:8000
"""

import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from supabase import Client, create_client

from bgg.auth import get_authenticated_session
from bgg.gencon import best_match, fetch_exhibitors
from bgg.geekpreview import (
    PRIORITY_LABELS,
    fetch_my_priorities,
    fetch_my_reactions,
    fetch_preview_items,
    fetch_preview_meta,
)

load_dotenv(Path(__file__).parent / ".env")

PREVIEW_ID = 92
GAMES_TABLE = "gencon_2026_games"
META_TABLE = "gencon_2026_meta"

app = FastAPI(title="GenCon 2026 Preview")

BGG_USERNAME = "indywiseguy"
BGG_PASSWORD = os.environ.get("BGG_PASSWORD", "")

_supabase: Client | None = None


def db() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _supabase


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


def fetch_bgg_collection(session: requests.Session) -> dict[str, dict]:
    """Fetch BGG collection status + wishlist comments for BGG_USERNAME using an
    already-authenticated session. Returns {objectid: {"status": str, "wishlist_comment": str}}."""
    # No excludesubtype filter — the GenCon preview list includes plenty of items
    # BGG classifies as "boardgameexpansion" (e.g. Root: Homeland Expansion), and
    # excluding that subtype silently drops their collection status entirely.
    url = "https://boardgamegeek.com/xmlapi2/collection"
    params = {
        "username": BGG_USERNAME,
        "subtype": "boardgame",
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
    result: dict[str, dict] = {}
    for item in root.findall("item"):
        oid = item.get("objectid", "")
        status_el = item.find("status")
        comment_el = item.find("wishlistcomment")
        result[oid] = {
            "status": _parse_status(status_el) if status_el is not None else "",
            "wishlist_comment": (comment_el.text or "").strip() if comment_el is not None else "",
        }
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _default_game_fields() -> dict:
    return {
        "bgg_status": "",
        "bgg_wishlist_comment": "",
        "bgg_preview_priority": "",
        "bgg_thumbsup": False,
        "interest_level": "",
        "hot_games_room": False,
        "rank": None,
        "tags": [],
    }


def _ensure_meta_row() -> None:
    res = db().table(META_TABLE).select("id").eq("id", 1).execute()
    if not res.data:
        db().table(META_TABLE).insert({"id": 1}).execute()


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/preview/refresh")
def refresh_preview():
    """Pull the latest public GeekPreview catalog (no login required) and
    fuzzy-match publishers to Gen Con booth numbers."""
    meta = fetch_preview_meta(PREVIEW_ID)
    items = fetch_preview_items(PREVIEW_ID)

    exhibitors = fetch_exhibitors()
    exhibitor_names = [e["name"] for e in exhibitors]
    booth_by_name = {e["name"]: e["booths"] for e in exhibitors}

    existing_by_id = {g["id"]: g for g in db().table(GAMES_TABLE).select("*").execute().data}

    # Publishers self-manage this list and occasionally submit the same game
    # twice under different itemids — dedupe by BGG game id, last one wins
    # (pagination order is itemid-ascending, so "last" is the most recent entry).
    merged_by_id: dict[str, dict] = {}
    added = 0
    for item in items:
        gid = item["id"]
        name, _score = best_match(item["publisher"], exhibitor_names)
        booth = booth_by_name.get(name, "N/A") if name else "N/A"

        existing = existing_by_id.get(gid)
        record = {**(existing or _default_game_fields())}
        record.update(item)  # keeps item["itemid"] — needed to join priorities/reactions later
        record["year"] = _to_int(item.get("year"))
        record["min_players"] = _to_int(item.get("min_players"))
        record["max_players"] = _to_int(item.get("max_players"))
        record["booth"] = booth
        record["still_in_preview"] = True
        if gid not in merged_by_id and existing is None:
            added += 1
        merged_by_id[gid] = record

    # Keep games that dropped off the live list (preserve tags/notes) but flag them
    for gid, existing in existing_by_id.items():
        if gid not in merged_by_id:
            existing["still_in_preview"] = False
            merged_by_id[gid] = existing

    rows = list(merged_by_id.values())
    db().table(GAMES_TABLE).upsert(rows, on_conflict="id").execute()

    last_refresh = time.strftime("%Y-%m-%d %H:%M")
    _ensure_meta_row()
    db().table(META_TABLE).update({
        "preview_title": meta.get("title", ""),
        "preview_start_date": meta.get("start_date", ""),
        "preview_end_date": meta.get("end_date", ""),
        "preview_location": meta.get("location", ""),
        "last_preview_refresh": last_refresh,
    }).eq("id", 1).execute()

    return {"ok": True, "total": len(rows), "added": added, "last_refresh": last_refresh}


@app.get("/api/bgg/refresh")
def refresh_bgg():
    """Log into BGG once and pull both GeekPreview personal data (priority/thumbs)
    and personal collection data (status + wishlist comments)."""
    if not BGG_PASSWORD:
        raise HTTPException(status_code=500, detail="BGG_PASSWORD not set in .env")

    session = get_authenticated_session(BGG_USERNAME, BGG_PASSWORD)

    userid, priorities = fetch_my_priorities(PREVIEW_ID, session)
    reactions = fetch_my_reactions(PREVIEW_ID, userid, list(priorities.keys()), session)
    collection = fetch_bgg_collection(session)

    games = db().table(GAMES_TABLE).select("*").execute().data
    updated = 0
    for game in games:
        itemid = game.get("itemid", "")
        priority_info = priorities.get(itemid, {})
        priority_label = PRIORITY_LABELS.get(priority_info.get("priority"), "")
        collection_info = collection.get(game["id"], {})

        new_status = collection_info.get("status", "")
        new_priority = priority_label
        new_wishlist_comment = collection_info.get("wishlist_comment", "")
        new_thumbsup = reactions.get(itemid, False)

        if (
            game.get("bgg_status") != new_status
            or game.get("bgg_preview_priority") != new_priority
            or game.get("bgg_wishlist_comment") != new_wishlist_comment
            or game.get("bgg_thumbsup") != new_thumbsup
        ):
            updated += 1
            db().table(GAMES_TABLE).update({
                "bgg_status": new_status,
                "bgg_preview_priority": new_priority,
                "bgg_wishlist_comment": new_wishlist_comment,
                "bgg_thumbsup": new_thumbsup,
            }).eq("id", game["id"]).execute()

    last_refresh = time.strftime("%Y-%m-%d %H:%M")
    _ensure_meta_row()
    db().table(META_TABLE).update({"last_bgg_refresh": last_refresh}).eq("id", 1).execute()
    return {"ok": True, "updated": updated, "last_refresh": last_refresh}


# ---------------------------------------------------------------------------
# Serve static files (must be last) — same static/ directory Netlify deploys
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
