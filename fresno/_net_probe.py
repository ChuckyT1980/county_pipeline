import asyncio, os, sys
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True, user_agent=UA,
            viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        log = []
        page.on("response", lambda res: log.append((res.status, res.url)))
        await page.goto("https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=09/10/26", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        # Click the Search popup
        try:
            await page.click("span.popup_search")
            await page.wait_for_timeout(2500)
            print("clicked search")
        except Exception as e:
            print("search click fail:", str(e)[:100])
        body = await page.evaluate("document.body ? document.body.innerText : ''")
        print("BODY (after search):", body[:2500])
        print()
        print("=== responses after search ===")
        for status, url in log[-8:]:
            print(status, url[:160])
        await ctx.close()

asyncio.run(main())
