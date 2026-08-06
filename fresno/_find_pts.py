"""Dump all links visible on the Fresno tax collector page + any tax-sale text."""
import asyncio, sys, re, json
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = "https://www.fresnocountyca.gov/Departments/Auditor-Controller-Treasurer-Tax-Collector"
        await page.goto(url, wait_until="networkidle", timeout=90000)
        await page.wait_for_timeout(3000)

        links = await page.evaluate(
            "Array.from(document.querySelectorAll('a')).map(a=>({t:a.innerText.trim().slice(0,80),h:(a.href||'')})).filter(x=>x.h||x.t)")
        print("total links:", len(links))
        for l in links:
            low = (l["t"] + " " + l["h"]).lower()
            if any(k in low for k in ["tax", "sale", "excess", "default", "delinquent", "power", "proceed", "auction"]):
                print(json.dumps(l))
        # also print body text around 'tax sale' / 'excess'
        body = await page.evaluate("document.body.innerText")
        for kw in ["Tax Sale", "excess proceeds", "Power to Sell", "Notice of Sale", "delinquent"]:
            idx = body.lower().find(kw.lower())
            if idx >= 0:
                print("CTX", kw, "->", body[max(0,idx-200):idx+300].replace("\n", " "))
        await ctx.close()

asyncio.run(main())
