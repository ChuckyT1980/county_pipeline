"""
Kern XHR capture — uses Playwright to perform a real search, records the network
request that fires, prints the exact endpoint + payload + headers so we can
replay it via curl-cffi at HTTP speed.

Run this ONCE to figure out the Kern search API contract, then use the printed
values to build a fast HTTP scraper (no browser needed for subsequent runs).

Usage:
    python kern_xhr_capture.py                    # captures search for one test APN
"""
import asyncio
import json
import re
from pathlib import Path


TEST_APN = "01902001"
SEARCH_URL = "https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx"
OUT = Path(__file__).parent / "kern_xhr_capture.json"


async def capture():
    from playwright.async_api import async_playwright

    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        page = await ctx.new_page()

        # Capture all requests + responses
        async def on_request(req):
            if req.method == "POST" and "kerncounty" in req.url:
                captured.append({
                    "phase": "request",
                    "url": req.url,
                    "method": req.method,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                })

        async def on_response(resp):
            req = resp.request
            if req.method == "POST" and "kerncounty" in req.url and resp.status < 400:
                try:
                    body = await resp.text()
                    captured.append({
                        "phase": "response",
                        "url": req.url,
                        "status": resp.status,
                        "body_len": len(body),
                        "body_preview": body[:2000],
                    })
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Loading search page...")
        await page.goto(SEARCH_URL, timeout=25000, wait_until="networkidle")

        # Select "APN" search type
        print("Selecting APN search type...")
        await page.select_option("select[name='ddlSearchType']", "apn")
        await asyncio.sleep(1)

        # Fill APN
        print(f"Filling test APN {TEST_APN}...")
        await page.fill("input[name='txtSearchText']", TEST_APN)
        await asyncio.sleep(0.5)

        # Click search
        print("Clicking search button...")
        try:
            await page.click("input[value='Search'], button:has-text('Search'), [id*='btnSearch']", timeout=5000)
        except Exception:
            # Fallback: trigger Enter key
            await page.press("input[name='txtSearchText']", "Enter")

        # Wait for search response
        await asyncio.sleep(5)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Take screenshot of result page
        result_html = await page.content()
        with open(Path(__file__).parent / "kern_result.html", "w", encoding="utf-8") as fp:
            fp.write(result_html)

        # Check for search results in the page text
        text = await page.evaluate("() => document.body.innerText")
        has_apn = TEST_APN in text
        print(f"\nResult page contains test APN: {has_apn}")
        print(f"Result page length: {len(text)} chars")
        if has_apn:
            idx = text.find(TEST_APN)
            print(f"Context: ...{text[max(0,idx-100):idx+300]}...")

        await browser.close()

    # Save captured requests
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(captured, fp, indent=2, default=str)

    print(f"\nCaptured {len(captured)} request/response events. Saved to {OUT}")
    print("\n--- REQUESTS captured ---")
    for i, evt in enumerate(captured):
        if evt.get("phase") == "request":
            print(f"\n[REQ #{i}] POST {evt['url']}")
            print(f"  Content-Type: {evt.get('headers',{}).get('content-type','?')}")
            if evt.get("post_data"):
                pd = evt["post_data"]
                if len(pd) > 500:
                    pd = pd[:500] + "...(truncated)"
                print(f"  Body preview: {pd}")


if __name__ == "__main__":
    asyncio.run(capture())
