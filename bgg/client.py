import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

BASE_URL = "https://boardgamegeek.com/xmlapi2"
_BATCH_SIZE = 20  # max IDs per /thing request
_MIN_DELAY = 2.0  # seconds between requests; BGG enforces ~30 req/min


class BGGError(Exception):
    pass


class BGGClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self._last_request_at: float = 0

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def search(self, query: str, type_: str = "boardgame") -> list[int]:
        """Return game IDs matching *query*."""
        root = self._get("search", {"query": query, "type": type_})
        return [int(item.get("id")) for item in root.findall("item")]

    def get_hot(self) -> list[int]:
        """Return IDs from the BGG hotness list."""
        root = self._get("hot", {"type": "boardgame"})
        return [int(item.get("id")) for item in root.findall("item")]

    def get_things(self, ids: list[int]) -> list[dict]:
        """Fetch full details for a batch of game IDs (max 20)."""
        if not ids:
            return []
        id_str = ",".join(str(i) for i in ids[:_BATCH_SIZE])
        root = self._get("thing", {"id": id_str, "type": "boardgame"})
        return [g for item in root.findall("item") if (g := self._parse_thing(item))]

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get(self, endpoint: str, params: Optional[dict] = None) -> ET.Element:
        self._rate_limit()
        url = f"{BASE_URL}/{endpoint}"
        for attempt in range(8):
            resp = self.session.get(url, params=params, timeout=30)
            self._last_request_at = time.time()

            if resp.status_code == 200:
                return ET.fromstring(resp.content)

            if resp.status_code == 202:
                # BGG is queuing the request server-side; back off and retry
                wait = min(2 ** attempt, 60)
                print(f"    [queued] waiting {wait}s...", flush=True)
                time.sleep(wait)
                self._rate_limit()
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10 * (attempt + 1)))
                print(f"    [rate limited] waiting {retry_after}s...", flush=True)
                time.sleep(retry_after)
                self._rate_limit()
                continue

            resp.raise_for_status()

        raise BGGError(f"BGG kept returning non-200 for {endpoint}")

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < _MIN_DELAY:
            time.sleep(_MIN_DELAY - elapsed)

    @staticmethod
    def _parse_thing(item: ET.Element) -> Optional[dict]:
        # The API call already requests type=boardgame, but guard explicitly
        # so expansions never slip through regardless of API behaviour.
        if item.get("type") != "boardgame":
            return None

        primary = item.find(".//name[@type='primary']")
        name = primary.get("value") if primary is not None else "Unknown"

        year_el = item.find("yearpublished")
        year = int(year_el.get("value")) if year_el is not None else None

        desc_el = item.find("description")
        description = (desc_el.text or "").strip() if desc_el is not None else ""

        publishers = [
            link.get("value")
            for link in item.findall(".//link[@type='boardgamepublisher']")
        ]

        return {
            "id": int(item.get("id")),
            "name": name,
            "year": year,
            "description": description,
            "publishers": publishers,
        }
