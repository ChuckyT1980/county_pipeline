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

        # accept disclaimer
        await page.goto("https://fresnocountyca-web.tylerhost.net/web/user/disclaimer", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.evaluate(
            """() => { const f = Array.from(document.querySelectorAll('form')).find(f => (f.action||'').includes('/web/user/disclaimer')); if (f) f.submit(); }""")
        await page.wait_for_timeout(8000)

        # go to APN search page
        await page.goto("https://fresnocountyca-web.tylerhost.net/web/search/DOCSEARCH377S5", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        print("URL:", page.url)
        print("TITLE:", await page.title())
        html = await page.content()
        # dump form fields
        fields = await page.evaluate(
            """() => Array.from(document.querySelectorAll('input, select, textarea')).map(e=>({t:e.type||e.tagName,n:e.name||'',id:e.id||'',ph:e.placeholder||''}))""")
        for f in fields:
            if f["t"] != "hidden":
                print("  FIELD:", f)
        body = await page.evaluate("document.body.innerText")
        print("\nBODY:", body[:1500])
        await ctx.close()

asyncio.run(main())
