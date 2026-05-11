"""
BGG geeklist automation.

Login flow:
  1. Use Playwright (headed) to authenticate — handles any Cloudflare challenges.
  2. Capture the GeekAuth token from a network request header.
  3. All subsequent API calls use that token via requests — fast, no browser needed.
"""

import json
import time
from typing import Optional

import requests
from playwright.sync_api import Page

_API = "https://api.geekdo.com/api"
_TIMEOUT = 20


def _headers(auth_token: str) -> dict:
    return {
        "Authorization": f"GeekAuth {auth_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://boardgamegeek.com",
        "Referer": "https://boardgamegeek.com/",
    }


def login_and_get_token(page: Page, username: str, password: str) -> str:
    """
    Log in via Playwright and return the GeekAuth token.

    The token is captured from the Authorization header the Angular app adds
    to any request it makes to api.geekdo.com after login.
    """
    captured: list[str] = []

    def on_req(req):
        auth = req.headers.get("authorization", "")
        if "api.geekdo.com" in req.url and auth.startswith("GeekAuth "):
            captured.append(auth[len("GeekAuth "):])

    page.on("request", on_req)

    # Log in
    page.goto("https://boardgamegeek.com/login", wait_until="load")
    page.wait_for_timeout(2000)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button:has-text("Sign In")')
    page.wait_for_timeout(6000)

    if "login" in page.url:
        raise RuntimeError(f"Login may have failed — still at {page.url}")

    # Wait for the Angular app to make an API call (gives us the token)
    deadline = time.time() + 10
    while not captured and time.time() < deadline:
        time.sleep(0.2)

    if not captured:
        raise RuntimeError("No GeekAuth token observed in network requests after login")

    token = captured[0]
    print(f"Logged in. GeekAuth token captured.")
    return token


def create_geeklist(
    auth_token: str,
    name: str,
    description: str = "",
    private: bool = True,
) -> int:
    """Create a geeklist and return its integer ID."""
    payload = {
        "name": name,
        "body": description,
        "publicAdditionsAllowed": True,
        "commentsAllowed": True,
        "private": private,
        "stealth": False,
        "trade": False,
        "sortType": "user",
        "domains": ["boardgame"],
        "ordinalDirection": "ascending",
    }
    r = requests.post(
        f"{_API}/geeklist",
        json=payload,
        headers=_headers(auth_token),
        timeout=_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_geeklist → {r.status_code}: {r.text[:300]}")
    gl_id = int(r.json()["id"])
    print(f"Created geeklist id={gl_id}: {name}")
    return gl_id


def add_item(
    auth_token: str,
    geeklist_id: int,
    game_id: int,
    body: str,
    index: int,
) -> Optional[int]:
    """Add one game to the geeklist. Returns the listitem id, or None on failure."""
    payload = {
        "item": {"type": "thing", "id": str(game_id)},
        "imageid": None,
        "imageOverridden": False,
        "index": index,
        "body": body,
        "rollsEnabled": False,
    }
    try:
        r = requests.post(
            f"{_API}/geeklist/{geeklist_id}/listitem",
            json=payload,
            headers=_headers(auth_token),
            timeout=_TIMEOUT,
        )
        if r.status_code not in (200, 201):
            print(f"  [WARN] add_item game {game_id} → {r.status_code}: {r.text[:200]}")
            return None
        return int(r.json()["listitem"]["id"])
    except Exception as exc:
        print(f"  [WARN] add_item game {game_id}: {exc}")
        return None


def delete_geeklist(auth_token: str, geeklist_id: int) -> bool:
    """Delete a geeklist. Returns True on success."""
    r = requests.delete(
        f"{_API}/geeklist/{geeklist_id}",
        headers=_headers(auth_token),
        timeout=_TIMEOUT,
    )
    return r.status_code in (200, 204)
