import asyncio, os, sys, re
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto("https://fresnocountyca-web.tylerhost.net/web/user/disclaimer", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.evaluate(
            """() => { const f = Array.from(document.querySelectorAll('form')).find(f => (f.action||'').includes('/web/user/disclaimer')); if (f) f.submit(); }""")
        await page.wait_for_timeout(8000)

        await page.goto("https://fresnocountyca-web.tylerhost.net/web/search/DOCSEARCH377S5", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2500)

        # fill APN search: try 090-101-15 (formatted) and 09010115
        for apn in ["090-101-15", "09010115"]:
            await page.fill("#field_ParcelID", apn)
            await page.wait_for_timeout(400)
            # click Search button
            try:
                await page.click("button:has-text('Search'), input[type=submit][value*=Search], #ss-search-button, input[type=submit]", timeout=8000)
            except Exception as e:
                print("search btn fail:", str(e)[:60])
            await page.wait_for_timeout(6000)
            print("=== APN", apn, "===")
            print("URL:", page.url)
            body = await page.evaluate("document.body.innerText")
            print(body[:1800])
            print()
            await ctx.close()
            return

asyncio.run(main())
