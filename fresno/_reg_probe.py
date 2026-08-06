import asyncio, os, sys, json
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
REG_URL = "https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=Register&zmethod=START"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(REG_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        for field, val in [("user_name", "chuckterrell740"), ("user_name", "chuckterrell740@gmail.com"),
                           ("email", "chuckterrell740@gmail.com")]:
            resp = await page.request.post(
                "https://fresnocounty.california.taxdefaultsale.com/index.cfm",
                headers={"X-Requested-With": "XMLHttpRequest"},
                form={"ZACTION": "REGISTER", "ZMETHOD": "VALIDATE",
                      "field_name": field, "field_data": val})
            body = await resp.text()
            import re
            m = re.search(r'\{[^{}]*"err_msg"[^{}]*\}', body)
            print(field, "=", val, "->", m.group(0) if m else body[:120].replace("\n", " "))
        await ctx.close()

asyncio.run(main())
