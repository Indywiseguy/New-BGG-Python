"""Fetch GenCon 2026 exhibitor list from the official API."""

import json
import re
from pathlib import Path

import requests

_API_URL = "https://www.gencon.com/api/v1/exhibitor_profiles"
_CONVENTION_ID = 27


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
