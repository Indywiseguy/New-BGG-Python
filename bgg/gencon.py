"""Fetch GenCon 2026 exhibitor list from the official API, and fuzzy-match
BGG publisher names against it to find booth numbers."""

import json
import re
from pathlib import Path

import requests
from rapidfuzz import fuzz, process

_API_URL = "https://www.gencon.com/api/v1/exhibitor_profiles"
_CONVENTION_ID = 27
MATCH_THRESHOLD = 91   # applied to _score(); lower to be more permissive

# BGG publisher values that are never real publishers
_SKIP_PUBLISHERS = {
    "(web published)", "self-published", "self published",
    "n/a", "", "unknown",
}


def _parse_booth(label: str) -> str:
    """'Exhibit Hall : Booth 1637' → 'Booth 1637'"""
    m = re.search(r"(Booth\s+\w+)", label, re.IGNORECASE)
    return m.group(1) if m else label.strip()


def fetch_exhibitors(
    cache_path: Path = Path("data/gencon_exhibitors.json"),
) -> list[dict]:
    """
    Return all Gen Con 2026 exhibitors as a list of
    {"name": str, "booths": str} dicts.

    Results are cached in data/gencon_exhibitors.json so the API is only
    hit once.  Delete that file to force a refresh.
    """
    if cache_path.exists():
        exhibitors = json.loads(cache_path.read_text())
        print(f"Loaded {len(exhibitors)} exhibitors from cache ({cache_path})")
        return exhibitors

    print("Fetching Gen Con 2026 exhibitor list...", flush=True)
    exhibitors = []
    page = 1

    while True:
        resp = requests.get(
            _API_URL,
            params={"c": _CONVENTION_ID, "page": page, "per_page": 25},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for e in data["exhibitors"]:
            booths = [_parse_booth(loc["label"]) for loc in e.get("locations", [])]
            exhibitors.append(
                {
                    "name": e["name"],
                    "booths": "; ".join(booths) if booths else "N/A",
                }
            )

        total = data["meta"]["totalPages"]
        print(f"\r  Page {page}/{total}", end="", flush=True)

        if page >= total:
            break
        page += 1

    print(f"\n  {len(exhibitors)} exhibitors fetched.")
    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(exhibitors, indent=2))
    return exhibitors


def _score(a: str, b: str, **_) -> float:
    """
    Combined scorer that handles two common cases:
    - One name is a clean prefix/substring of the other
      ("CMON" ↔ "CMON Limited", "Asmodee" ↔ "Asmodee North America")
      → partial_ratio fires at 100, upgrade to it.
    - Names differ only by typos, plurals, punctuation
      ("Renegade Game Studios" ↔ "Renegade Game Studio")
      → QRatio handles this well.

    We only upgrade to partial_ratio when it is ≥ 95 *and* the shorter
    string is at least 4 characters, which prevents single common words
    like "Games" from creating false positives.
    """
    q  = fuzz.QRatio(a, b)
    pr = fuzz.partial_ratio(a, b)
    if pr >= 95 and min(len(a), len(b)) >= 4:
        return pr
    return q


def best_match(
    publisher_field: str,
    exhibitor_names: list[str],
) -> tuple[str | None, float]:
    """
    Try each semicolon-separated publisher in *publisher_field* and return
    (best_exhibitor_name, score), or (None, 0) if nothing meets the threshold.
    """
    publishers = [p.strip() for p in publisher_field.split(";")]
    best_name: str | None = None
    best_score: float = 0

    for pub in publishers:
        if pub.lower() in _SKIP_PUBLISHERS:
            continue
        result = process.extractOne(pub, exhibitor_names, scorer=_score)
        if result and result[1] >= MATCH_THRESHOLD and result[1] > best_score:
            best_name, best_score = result[0], result[1]

    return best_name, best_score
