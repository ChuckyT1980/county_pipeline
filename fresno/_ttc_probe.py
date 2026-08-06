import asyncio, os
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
OUT = r"C:\Users\chuck\Downloads\county_pipeline\fresno"

URLS = [
    "https://www.fresnocountyca.gov/departments/auditor-controller-treasurer-tax-collector/tax-sale",
    "https://www.fresnocountyca.gov/departments/auditor-controller-treasurer-tax-collector/tax-sale-amp-excess-proceeds",
    "https://www.fresnocountyca.gov/departments/auditor-controller-treasurer-tax-collector",
]

async def main():
    os.makedirs(SESSION_DIR, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for url in URLS:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                title = await page.title()
                print("URL:", url)
                print("  status:", await page.evaluate("document.title"))
                print("  h1/h2:", await page.evaluate(
                    "Array.from(document.querySelectorAll('h1,h2,h3')).slice(0,8).map(e=>e.innerText.trim()).join(' | ')"))
                # find links to pdf/xlsx lists
                links = await page.evaluate(
                    "Array.from(document.querySelectorAll('a[href]')).filter(a=>/pdf|notice|list|auction|sale|default/i.test(a.href+a.innerText)).slice(0,25).map(a=>({t:a.innerText.trim(),h:a.href}))")
                for l in links:
                    print("   LINK:", l["t"][:70], "=>", l["h"][:110])
                print()
            except Exception as e:
                print("ERR", url, type(e).__name__, str(e)[:100])
        await ctx.close()

asyncio.run(main())
