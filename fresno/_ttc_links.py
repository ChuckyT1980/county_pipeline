import asyncio, os
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = "https://www.fresnocountyca.gov/Departments/Auditor-Controller-Treasurer-Tax-Collector/Property-Tax-Information/Tax-Sale-Excess-Proceeds"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Only links inside the main content area, and only real docs
        links = await page.evaluate(
            """
            () => {
              const main = document.querySelector('main, #main, #main-content') || document;
              return Array.from(main.querySelectorAll('a[href]'))
                .map(a => ({t: a.innerText.trim(), h: a.href}))
                .filter(l => /\.(pdf|xlsx?|docx?|csv)$/i.test(l.h) || /notice|sale|auction|list|default|bidder|excess|delinquent/i.test(l.t + ' ' + l.h));
            }
            """)
        seen = set()
        for l in links:
            if l["h"] in seen or not l["t"]: continue
            seen.add(l["h"])
            safe_t = l["t"].encode("ascii", "replace").decode()[:80]
            print(safe_t, "=>", l["h"][:170])
        await ctx.close()

asyncio.run(main())
