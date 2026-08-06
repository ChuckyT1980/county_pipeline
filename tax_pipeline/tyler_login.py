"""Launch Tyler portal in non-headless mode for manual login.
After login, test a recorder name search."""

import sys
sys.path.insert(0, ".")

from butte_recorder_adapter import ButteRecorderAdapter

import time

adapter = ButteRecorderAdapter(headless=False)
adapter.start()
print("Browser launched in non-headless mode.")
print("Log in to the Tyler portal in the visible browser window.")
print("Navigate to the search page if it doesn't go there automatically.")
print("Waiting 120 seconds for you to log in...")
# Poll every 5s checking if we're still on a login/disclaimer page
for i in range(24):
    time.sleep(5)
    if adapter._page:
        url = adapter._page.url
        print(f"  [{i*5+5}s] Current URL: {url}")
        if "DOCSEARCH481S1" in url.lower() or "DOCSEARCH" in url:
            print("Search page detected! Continuing...")
            break
        if "disclaimer" in url.lower():
            try:
                adapter._accept_disclaimer()
                print("  Accepted disclaimer")
            except:
                pass

if "DOCSEARCH" not in adapter._page.url:
    print("Did not reach search page within timeout. You can still log in manually.")
    print("The browser will stay open for 120 more seconds...")
    time.sleep(120)
    print(f"Final URL: {adapter._page.url}")

# Test with a known owner from our auction data
test_names = [
    "2585 ORO DAM LLC",
    "MORRIS ELIZABETH",
    "BALLARD-RODRIGUEZ",
]

for name in test_names:
    print(f"\nSearching: {name}")
    try:
        events = adapter.name_search(name)
        print(f"  Found {len(events)} events")
        for e in events[:8]:
            print(f"  {e['doc_number']} {str(e['recorded_date'])[:10]} {e['doc_type'][:20]} | {str(e['grantor'])[:50]} -> {str(e['grantee'])[:50]}")
    except Exception as ex:
        print(f"  Error: {ex}")

print("\nDone. Closing browser.")
# Save cookies for future headless use
try:
    cookies = adapter._browser.contexts[0].cookies()
    import json
    with open("tyler_session_cookies.json", "w") as f:
        json.dump(cookies, f)
    print(f"Saved {len(cookies)} cookies to tyler_session_cookies.json")
except Exception as ex:
    print(f"Could not save cookies: {ex}")

adapter.close()
print("Browser closed. Session cookies saved for future headless runs.")
