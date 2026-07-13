"""
Shared BGG login helper.

BGG's XML/REST APIs return 401/403 for private or user-specific data when
called unauthenticated, and Cloudflare blocks headless browsers. We log in
via a headed Playwright browser (handles any Cloudflare challenge), copy the
resulting session cookies into a requests.Session, and close the browser —
all subsequent calls are then fast, cookie-authenticated plain requests.
"""

import requests
from playwright.sync_api import sync_playwright


def get_authenticated_session(username: str, password: str) -> requests.Session:
    """Log into BGG and return a requests.Session carrying the session cookies."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto("https://boardgamegeek.com/login", wait_until="load")
            page.wait_for_timeout(2000)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button:has-text("Sign In")')
            page.wait_for_timeout(6000)
            if "login" in page.url:
                raise RuntimeError("BGG login failed — check credentials in .env")
            all_cookies = context.cookies()
        finally:
            browser.close()

    session = requests.Session()
    for c in all_cookies:
        session.cookies.set(c["name"], c["value"])
    return session
