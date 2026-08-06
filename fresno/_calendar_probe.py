"""Check the Realauction auction calendar for upcoming Fresno auctions."""
import asyncio, os, sys, json
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=AUCTION&Zmethod=CALENDAR",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        body = await page.evaluate("document.body.innerText")
        print(body.encode("ascii", "replace").decode()[:2500])
        await ctx.close()

asyncio.run(main())
