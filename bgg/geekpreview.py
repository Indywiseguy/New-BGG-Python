"""
BGG "GeekPreview" API — the first-party curated preview lists BGG runs for
conventions (e.g. https://boardgamegeek.com/geekpreview/92/gen-con-2026-preview),
distinct from user-created geeklists.

Catalog data (geekpreviews / geekpreviewitems) is public — plain requests,
no login required. Personal data (userinfo / reactions) requires an
authenticated session — see bgg/auth.py.
"""

import time
from typing import Optional

import requests

_GEEKDO_API = "https://api.geekdo.com/api"
_BGG_API = "https://boardgamegeek.com/api"
_PAGE_DELAY = 0.25
_REACTIONS_CHUNK = 150

PRIORITY_LABELS = {1: "Must Have", 2: "Interested", 3: "Undecided", 4: "Not Interested"}


def fetch_preview_meta(previewid: int) -> dict:
    r = requests.get(f"{_GEEKDO_API}/geekpreviews", params={"nosession": 1, "previewid": previewid}, timeout=20)
    r.raise_for_status()
    d = r.json()
    return {
        "title": d.get("title", ""),
        "start_date": d.get("start_date", ""),
        "end_date": d.get("end_date", ""),
        "location": d.get("location", ""),
    }


def _parse_item(raw: dict) -> dict:
    item = raw.get("geekitem", {}).get("item", {})
    publishers = raw.get("publishers") or []
    publisher_names = [
        p["item"]["primaryname"]["name"]
        for p in publishers
        if p.get("item", {}).get("primaryname", {}).get("name")
    ]
    stats = raw.get("stats") or {}
    reactions = raw.get("reactions") or {}

    return {
        "itemid": raw.get("itemid", ""),
        "id": str(raw.get("objectid", "")),
        "name": item.get("primaryname", {}).get("name", "Unknown"),
        "year": item.get("yearpublished"),
        "min_players": item.get("minplayers"),
        "max_players": item.get("maxplayers"),
        "publisher": "; ".join(publisher_names),
        "thumbnail": (raw.get("thumbnail") or {}).get("src", ""),
        "msrp": raw.get("msrp"),
        "showprice": raw.get("showprice"),
        "currency": raw.get("showprice_currency") or raw.get("msrp_currency") or "",
        "availability_status": raw.get("pretty_availability_status", ""),
        "community_musthave": stats.get("musthave", 0),
        "community_interested": stats.get("interested", 0),
        "community_undecided": stats.get("undecided", 0),
        "community_thumbs": reactions.get("thumbs", 0),
    }


def fetch_preview_items(previewid: int) -> list[dict]:
    """Fetch every item in the preview list (paginated, 10/page, public)."""
    items: list[dict] = []
    session = requests.Session()
    page = 1
    while True:
        r = session.get(
            f"{_GEEKDO_API}/geekpreviewitems",
            params={"nosession": 1, "pageid": page, "previewid": previewid},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        items.extend(_parse_item(raw) for raw in batch)
        page += 1
        time.sleep(_PAGE_DELAY)
    return items


def fetch_booth_by_itemid(previewid: int) -> dict[str, str]:
    """Return {itemid: booth/location}, sourced directly from BGG's own preview
    list — publishers self-report their booth on the "parent" (company) entry
    that groups their preview items, via geekpreviewparentitems. This is the
    authoritative source; only fall back to fuzzy-matching Gen Con's exhibitor
    list (bgg/gencon.py) for the publishers who haven't filled this in on BGG."""
    result: dict[str, str] = {}
    session = requests.Session()
    page = 1
    while True:
        r = session.get(
            f"{_GEEKDO_API}/geekpreviewparentitems",
            params={"nosession": 1, "pageid": page, "previewid": previewid},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for parent in batch:
            location = (parent.get("location") or "").strip()
            if not location:
                continue
            for itemid in parent.get("previewitemids") or []:
                result[itemid] = location
        page += 1
        time.sleep(_PAGE_DELAY)
    return result


def fetch_my_priorities(previewid: int, session: requests.Session) -> tuple[str, dict[str, dict]]:
    """Return (userid, {itemid: {"priority": int|None, "notes": str}}) for the logged-in user."""
    r = session.get(f"{_BGG_API}/geekpreviewitems/userinfo", params={"previewid": previewid}, timeout=20)
    r.raise_for_status()
    d = r.json()
    userid = str(d.get("userid", ""))
    result = {
        itemid: {"priority": info.get("priority"), "notes": info.get("notes") or ""}
        for itemid, info in (d.get("items") or {}).items()
    }
    return userid, result


def fetch_my_reactions(
    previewid: int, userid: str, itemids: list[str], session: requests.Session
) -> dict[str, bool]:
    """Return {itemid: thumbsup_bool} for the logged-in user."""
    result: dict[str, bool] = {}
    for i in range(0, len(itemids), _REACTIONS_CHUNK):
        chunk = itemids[i : i + _REACTIONS_CHUNK]
        r = session.get(
            f"{_BGG_API}/users/{userid}/reactions",
            params={"previewitems": ",".join(chunk)},
            timeout=20,
        )
        r.raise_for_status()
        for itemid, reactions in (r.json().get("previewitems") or {}).items():
            result[itemid] = bool(reactions.get("thumbsup"))
    return result
