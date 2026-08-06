"""Capture all XHR/network requests on the preview page to find the items endpoint."""
import asyncio, os, sys, json
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
LOGIN_URL = "https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=Login&zmethod=START"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        async def log_request(req):
            if req.resource_type in ("xhr", "fetch") or "index.cfm" in req.url or "zaction" in req.url:
                print(f"REQ {req.method} {req.url[:160]}")
                if req.method == "POST" and req.post_data:
                    print(f"    BODY: {req.post_data[:200]}")

        async def log_response(resp):
            if resp.request.resource_type in ("xhr", "fetch") or "zaction" in resp.request.url:
                ct = resp.headers.get("content-type", "")
                if "json" in ct or "text" in ct:
                    try:
                        body = await resp.text()
                        if len(body) < 300000:
                            print(f"RES {resp.request.method} {resp.request.url[:140]} [{len(body)}b] {ct}")
                            if "json" in ct:
                                print(f"    JSON: {body[:400]}")
                    except Exception:
                        pass

        page.on("request", log_request)
        page.on("response", log_response)

        # login
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.fill("#LogName", "chuckterrell740@gmail.com")
        await page.fill("#LogPass", "Td!lu7p1VFy1L2J6a")
        await page.click("#LogButton")
        await page.wait_for_timeout(5000)

        print("\n--- PREVIEW 09/10/26 ---")
        await page.goto("https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=09/10/26",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        # click any calendar/date links present
        links = await page.evaluate(
            "Array.from(document.querySelectorAll('a')).map(a=>({t:a.innerText.trim().slice(0,40),href:(a.href||'')})).filter(x=>/auction/i.test(x.href)||/date/i.test(x.href)||/calendar/i.test(x.href))")
        print("AUCTION LINKS:", json.dumps(links, indent=1))

        await ctx.close()

asyncio.run(main())
