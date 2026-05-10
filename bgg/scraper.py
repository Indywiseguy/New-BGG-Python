"""
Scrape BGG's year-filtered advanced search using a headed (visible) browser.

Headed mode is required because Cloudflare blocks headless Chromium. A
browser window will open and close automatically — don't close it manually.

Results are cached in data/ids_<year_min>_<year_max>.json so the browser
is not needed on subsequent runs.
"""

import json
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

_SEARCH_URL = (
    "https://boardgamegeek.com/search/boardgame/page/{page}"
    "?advsearch=1&q="
    "&range%5Byearpublished%5D%5Bmin%5D={year_min}"
    "&range%5Byearpublished%5D%5Bmax%5D={year_max}"
    "&B1=Submit"
)
_RESULTS_TABLE = "#collectionitems"


def _ids_from_page(html: str) -> set[int]:
    start = html.find('id="collectionitems"')
    end = html.find("</table>", start)
    if start == -1 or end == -1:
        return set()
    return {int(m) for m in re.findall(r'/boardgame/(\d+)/', html[start:end])}


def _total_pages(html: str) -> int:
    pages = [int(p) for p in re.findall(r'/page/(\d+)', html)]
    return max(pages, default=1)


def collect_ids(
    year_min: int,
    year_max: int,
    cache_dir: Path = Path("data"),
) -> list[int]:
    """
    Return all BGG base-game IDs for the given year range scraped from the
    advanced search.  Expansions are excluded at the XML API level later;
    the scraper collects whatever the search returns.
    Caches results in data/ids_<year_min>_<year_max>.json.
    """
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"ids_{year_min}_{year_max}.json"

    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached:
            print(f"Loaded {len(cached):,} cached IDs from {cache_file}")
            return cached

    print(
        "Opening Chromium to fetch BGG search results (Cloudflare requires a real browser).\n"
        "A window will appear briefly — do not close it.\n"
    )

    all_ids: set[int] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        pg = browser.new_page()

        # --- Page 1: load it and discover total page count ---
        pg.goto(
            _SEARCH_URL.format(page=1, year_min=year_min, year_max=year_max),
            wait_until="load",
            timeout=60_000,
        )
        try:
            pg.wait_for_selector(_RESULTS_TABLE, timeout=30_000)
        except PlaywrightTimeout:
            print("Results table never appeared — Cloudflare may have blocked the browser.")
            browser.close()
            return []

        time.sleep(2)   # let Angular finish any remaining renders
        content = pg.content()
        pages = _total_pages(content)
        page_ids = _ids_from_page(content)
        all_ids.update(page_ids)
        print(f"  Page  1/{pages}: {len(page_ids)} IDs  (running total: {len(all_ids)})")

        # --- Remaining pages ---
        for page_num in range(2, pages + 1):
            pg.goto(
                _SEARCH_URL.format(page=page_num, year_min=year_min, year_max=year_max),
                wait_until="load",
                timeout=60_000,
            )
            try:
                pg.wait_for_selector(_RESULTS_TABLE, timeout=30_000)
            except PlaywrightTimeout:
                print(f"\n  Page {page_num}: timeout — stopping early.")
                break

            time.sleep(2)
            content = pg.content()
            page_ids = _ids_from_page(content) - all_ids

            if not page_ids:
                print(f"\n  Page {page_num}: no new IDs — done.")
                break

            all_ids.update(page_ids)
            print(
                f"\r  Page {page_num:2d}/{pages}: {len(page_ids):3d} IDs  "
                f"(running total: {len(all_ids)})",
                end="",
                flush=True,
            )

        browser.close()

    sorted_ids = sorted(all_ids)
    cache_file.write_text(json.dumps(sorted_ids))
    print(f"\nDone. {len(sorted_ids):,} IDs cached to {cache_file}")
    return sorted_ids
