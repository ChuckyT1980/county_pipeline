"""Log into Fresno Realauction and pull the auction preview item list."""
import asyncio, os, sys, json, re
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
LOGIN_URL = "https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=Login&zmethod=START"

USER = "chuckterrell740@gmail.com"
PASS = "Td!lu7p1VFy1L2J6a"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        await page.fill("#LogName", USER)
        await page.fill("#LogPass", PASS)
        await page.wait_for_timeout(300)
        await page.click("#LogButton")
        await page.wait_for_timeout(6000)

        print("AFTER LOGIN URL:", page.url)
        body = await page.evaluate("document.body.innerText")
        print("AFTER LOGIN:", body[:400].encode("ascii", "replace").decode())

        if "Invalid" in body:
            print("LOGIN REJECTED")
            await ctx.close()
            return

        for date in ["09/10/26", "09/11/26"]:
            url = f"https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date}"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            body = await page.evaluate("document.body.innerText")
            print(f"\n===== PREVIEW {date} =====")
            print(body[:600].encode("ascii", "replace").decode())
            html = await page.content()
            open(rf"fresno\_preview_{date.replace('/','')}.html", "w", encoding="utf-8").write(html)
            print("saved", len(html), "bytes")
        await ctx.close()

asyncio.run(main())
