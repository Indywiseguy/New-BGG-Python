"""
Export BGG collection (including private comments) to a CSV file.

Strategy:
  1. Log in via Playwright and download BGG's native CSV export — the only
     source that returns privatecomment and private ownership fields.
  2. Fetch the XML API /collection endpoint (one call) for fields missing
     from the native CSV: image URL, thumbnail, min_age, status_last_modified,
     family/category ranks, num_ratings, rating_stddev.
  3. Merge by game ID and write the combined output.

Usage:
    python export_collection.py

Requires BGG_PASSWORD in .env (BGG_USERNAME defaults to "indywiseguy").
Output: data/bgg_collection.csv
"""

import csv
import io
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

from bgg.auth import get_authenticated_session

load_dotenv(Path(__file__).parent / ".env")

BGG_USERNAME = os.environ.get("BGG_USERNAME", "indywiseguy")
BGG_PASSWORD = os.environ["BGG_PASSWORD"]
OUTPUT_FILE  = Path("data/bgg_collection.csv")

# Column order in the final CSV
CSV_FIELDS = [
    # Identity
    "id",
    "collid",
    "name",
    "original_name",
    "year_published",
    "image",
    "thumbnail",
    "image_id",
    # Game info
    "min_players",
    "max_players",
    "min_playtime",
    "max_playtime",
    "playing_time",
    "min_age",
    "avg_weight",
    "num_owned",
    "bgg_rec_players",
    "bgg_best_players",
    "bgg_rec_age_range",
    "bgg_language_dependence",
    # Collection status flags
    "own",
    "preordered",
    "wanttobuy",
    "wishlist",
    "wishlist_priority",
    "wanttoplay",
    "want",
    "fortrade",
    "prevowned",
    "quantity",
    "status_last_modified",
    # Play tracking
    "num_plays",
    # Ratings
    "rating",
    "bgg_rating",
    "bgg_geek_rating",
    "num_ratings",
    "rating_stddev",
    # BGG ranks
    "bgg_rank",
    "family_ranks",
    # Private ownership / inventory fields
    "acquiredfrom",
    "acquisition_date",
    "inv_date",
    "price_paid",
    "price_paid_currency",
    "curr_value",
    "curr_value_currency",
    "inv_location",
    "condition",
    "want_parts_list",
    "has_parts_list",
    "barcode",
    # Version info
    "version_publishers",
    "version_languages",
    "version_year_published",
    "version_nickname",
    # Comments
    "wishlist_comment",
    "comment",
    "private_comment",
]


# ---------------------------------------------------------------------------
# Step 1: Download BGG native CSV via Playwright (has private fields)
# ---------------------------------------------------------------------------

def _download_native_csv() -> list[dict]:
    print("Launching browser to log in to BGG...", flush=True)
    session = get_authenticated_session(BGG_USERNAME, BGG_PASSWORD)
    print("Login succeeded. Downloading native CSV...", flush=True)

    export_url = (
        f"https://boardgamegeek.com/geekcollection.php"
        f"?action=exportcsv&subtype=boardgame&username={BGG_USERNAME}&all=1"
    )
    resp = session.get(export_url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"CSV export returned HTTP {resp.status_code}")
    csv_bytes = resp.content

    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"Native CSV: {len(rows)} rows, {len(rows[0])} columns", flush=True)
    return rows


def _parse_native_row(r: dict) -> dict:
    return {
        "id":                       r.get("objectid", ""),
        "collid":                   r.get("collid", ""),
        "name":                     r.get("objectname", ""),
        "original_name":            r.get("originalname", ""),
        "year_published":           r.get("yearpublished", ""),
        "image":                    "",   # filled by XML step
        "thumbnail":                "",   # filled by XML step
        "image_id":                 r.get("imageid", ""),
        "min_players":              r.get("minplayers", ""),
        "max_players":              r.get("maxplayers", ""),
        "min_playtime":             r.get("minplaytime", ""),
        "max_playtime":             r.get("maxplaytime", ""),
        "playing_time":             r.get("playingtime", ""),
        "min_age":                  "",   # filled by XML step
        "avg_weight":               r.get("avgweight", ""),
        "num_owned":                r.get("numowned", ""),
        "bgg_rec_players":          r.get("bggrecplayers", ""),
        "bgg_best_players":         r.get("bggbestplayers", ""),
        "bgg_rec_age_range":        r.get("bggrecagerange", ""),
        "bgg_language_dependence":  r.get("bgglanguagedependence", ""),
        "own":                      r.get("own", "0"),
        "preordered":               r.get("preordered", "0"),
        "wanttobuy":                r.get("wanttobuy", "0"),
        "wishlist":                 r.get("wishlist", "0"),
        "wishlist_priority":        r.get("wishlistpriority", ""),
        "wanttoplay":               r.get("wanttoplay", "0"),
        "want":                     r.get("want", "0"),
        "fortrade":                 r.get("fortrade", "0"),
        "prevowned":                r.get("prevowned", "0"),
        "quantity":                 r.get("quantity", ""),
        "status_last_modified":     "",   # filled by XML step
        "num_plays":                r.get("numplays", ""),
        "rating":                   r.get("rating", ""),
        "bgg_rating":               r.get("average", ""),
        "bgg_geek_rating":          r.get("baverage", ""),
        "num_ratings":              "",   # filled by XML step
        "rating_stddev":            "",   # filled by XML step
        "bgg_rank":                 r.get("rank", ""),
        "family_ranks":             "",   # filled by XML step
        "acquiredfrom":             r.get("acquiredfrom", ""),
        "acquisition_date":         r.get("acquisitiondate", ""),
        "inv_date":                 r.get("invdate", ""),
        "price_paid":               r.get("pricepaid", ""),
        "price_paid_currency":      r.get("pp_currency", ""),
        "curr_value":               r.get("currvalue", ""),
        "curr_value_currency":      r.get("cv_currency", ""),
        "inv_location":             r.get("invlocation", ""),
        "condition":                r.get("conditiontext", ""),
        "want_parts_list":          r.get("wantpartslist", ""),
        "has_parts_list":           r.get("haspartslist", ""),
        "barcode":                  r.get("barcode", ""),
        "version_publishers":       r.get("version_publishers", ""),
        "version_languages":        r.get("version_languages", ""),
        "version_year_published":   r.get("version_yearpublished", ""),
        "version_nickname":         r.get("version_nickname", ""),
        "wishlist_comment":         r.get("wishlistcomment", ""),
        "comment":                  r.get("comment", ""),
        "private_comment":          r.get("privatecomment", ""),
    }


# ---------------------------------------------------------------------------
# Step 2: Fetch XML API collection for supplemental fields
# ---------------------------------------------------------------------------

def _fetch_xml_collection() -> dict[str, dict]:
    """Returns a dict keyed by game ID with supplemental XML-only fields."""
    session = requests.Session()
    session.post(
        "https://boardgamegeek.com/login/api/v1",
        json={"credentials": {"username": BGG_USERNAME, "password": BGG_PASSWORD}},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    url = "https://boardgamegeek.com/xmlapi2/collection"
    params = {
        "username": BGG_USERNAME,
        "subtype": "boardgame",
        "stats": "1",
    }
    print("Fetching XML collection for supplemental fields...", flush=True)
    for attempt in range(12):
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 200:
            break
        if r.status_code == 202:
            wait = min(5 * (attempt + 1), 60)
            print(f"  BGG queued the request, retrying in {wait}s...", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 30))
            time.sleep(retry_after)
            continue
        r.raise_for_status()
    else:
        raise RuntimeError("BGG XML API timed out")

    root = ET.fromstring(r.content)
    result: dict[str, dict] = {}
    for item in root.findall("item"):
        game_id     = item.get("objectid", "")
        status      = item.find("status")
        stats       = item.find("stats")
        rating_el   = stats.find("rating") if stats is not None else None
        bayes_el    = rating_el.find("bayesaverage") if rating_el is not None else None
        users_el    = rating_el.find("usersrated")   if rating_el is not None else None
        stddev_el   = rating_el.find("stddev")       if rating_el is not None else None

        bgg_rank     = ""
        family_ranks = []
        if rating_el is not None:
            for rank in rating_el.findall(".//rank"):
                val = rank.get("value", "")
                if rank.get("name") == "boardgame":
                    bgg_rank = "" if val in ("Not Ranked", "") else val
                else:
                    friendly = rank.get("friendlyname", rank.get("name", ""))
                    if val and val != "Not Ranked":
                        family_ranks.append(f"{friendly}: {val}")

        def _t(tag):
            child = item.find(tag)
            return (child.text or "").strip() if child is not None else ""

        result[game_id] = {
            "image":                _t("image"),
            "thumbnail":            _t("thumbnail"),
            "min_age":              stats.get("minage", "") if stats is not None else "",
            "status_last_modified": status.get("lastmodified", "") if status is not None else "",
            "num_ratings":          users_el.get("value", "") if users_el is not None else "",
            "rating_stddev":        stddev_el.get("value", "") if stddev_el is not None else "",
            "bgg_geek_rating":      bayes_el.get("value", "") if bayes_el is not None else "",
            "bgg_rank":             bgg_rank,
            "family_ranks":         "; ".join(family_ranks),
        }

    print(f"XML collection: {len(result)} items", flush=True)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_collection_rows() -> list[dict]:
    """Log into BGG, pull the native CSV export + the supplemental XML fields,
    merge them, and return the combined rows (sorted by name). This is the
    single source of truth for "what's in my BGG collection" — reused by both
    the CSV export (below) and the Postgres sync pipeline."""
    native_rows = _download_native_csv()
    xml_data    = _fetch_xml_collection()

    rows = []
    for nr in native_rows:
        row  = _parse_native_row(nr)
        supp = xml_data.get(row["id"], {})
        for field, value in supp.items():
            if value:  # don't overwrite with empty
                row[field] = value
        rows.append(row)

    rows.sort(key=lambda r: r["name"].lower())
    return rows


def main():
    rows = fetch_collection_rows()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    private_count = sum(1 for r in rows if r["private_comment"].strip())
    print(f"Wrote {len(rows)} games to {OUTPUT_FILE} ({private_count} with private comments)", flush=True)


if __name__ == "__main__":
    main()
