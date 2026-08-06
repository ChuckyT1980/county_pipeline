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

        def on_request(req):
            if "searchPost" in req.url or "searchResults" in req.url:
                print("=== ", req.method, req.url[:110])
                print("   cookie:", req.headers.get("cookie"))
                if "searchPost" in req.url:
                    print("   body:", req.post_data)

        page.on("request", on_request)

        await page.goto("https://fresnocountyca-web.tylerhost.net/web/user/disclaimer", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.evaluate(
            """() => { const f = Array.from(document.querySelectorAll('form')).find(f => (f.action||'').includes('/web/user/disclaimer')); if (f) f.submit(); }""")
        await page.wait_for_timeout(8000)
        await page.goto("https://fresnocountyca-web.tylerhost.net/web/search/DOCSEARCH377S5", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2500)
        cookies = await ctx.cookies()
        print("COOKIES:")
        for ck in cookies:
            print("  ", ck.get("name"), "=", (ck.get("value") or "")[:40])
        await page.fill("#field_ParcelID", "090-101-15")
        await page.wait_for_timeout(800)
        await page.click("#searchButton")
        await page.wait_for_timeout(6000)
        await ctx.close()

asyncio.run(main())
