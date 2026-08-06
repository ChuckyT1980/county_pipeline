import asyncio, os
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = "https://www.fresnocountyca.gov/Departments/Auditor-Controller-Treasurer-Tax-Collector/Property-Tax-Information/Tax-Sale-Excess-Proceeds"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        links = await page.evaluate(
            """
            () => {
              const main = document.querySelector('main, #main, #main-content') || document;
              return Array.from(main.querySelectorAll('a[href]')).map(a=>({t:a.innerText.trim(), h:a.href}))
                .filter(l => /excess|proceed|claim|owner|form|notice/i.test(l.t + ' ' + l.h));
            }
            """)
        seen = set()
        for l in links:
            if l["h"] in seen: continue
            seen.add(l["h"])
            safe_t = l["t"].encode("ascii", "replace").decode()[:80]
            print(safe_t, "=>", l["h"][:150])
        await ctx.close()

asyncio.run(main())
