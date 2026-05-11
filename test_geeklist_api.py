"""
End-to-end test: login, create geeklist, add 2 items, verify, delete.
"""

import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bgg.geeklist import login_and_get_token, create_geeklist, add_item, delete_geeklist

load_dotenv()

USERNAME = "indywiseguy"
PASSWORD = os.environ["BGG_PASSWORD"]

# Two well-known BGG game IDs for testing
TEST_GAMES = [
    (174430, "Gloomhaven"),
    (161936, "Pandemic Legacy Season 1"),
]


def main():
    print("=== BGG Geeklist API End-to-End Test ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context()
        page = ctx.new_page()
        auth_token = login_and_get_token(page, USERNAME, PASSWORD)
        browser.close()

    print(f"Auth token: {auth_token[:20]}...")

    # Create
    print("\n--- create_geeklist ---")
    try:
        gl_id = create_geeklist(auth_token, "TEST - DELETE ME", private=True)
        print(f"PASS: id={gl_id}")
    except Exception as e:
        print(f"FAIL: {e}")
        return

    # Add items
    print("\n--- add_item ---")
    for idx, (game_id, name) in enumerate(TEST_GAMES, start=1):
        time.sleep(1)
        item_id = add_item(auth_token, gl_id, game_id, f"Test body for {name}", index=idx)
        if item_id:
            print(f"PASS: {name} → listitem id={item_id}")
        else:
            print(f"FAIL: {name}")

    # Delete
    print("\n--- delete_geeklist ---")
    time.sleep(1)
    ok = delete_geeklist(auth_token, gl_id)
    print(f"{'PASS' if ok else 'FAIL'}: delete geeklist {gl_id}")

    print("\n=== Test complete ===")


if __name__ == "__main__":
    main()
