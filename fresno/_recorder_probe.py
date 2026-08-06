import asyncio, os, sys
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.fresnocountyca.gov/Services/Recorded-Documents-Search", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        print("URL:", page.url)
        print("TITLE:", await page.title())
        # dump all iframes and links
        frames = await page.evaluate("Array.from(document.querySelectorAll('iframe')).map(f=>({src:f.src,id:f.id}))")
        print("IFRAMES:", frames)
        links = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]')).map(a=>({t:a.innerText.trim(),h:a.href})).filter(l=>l.h && !/fresnocountyca|library|facebook|twitter|instagram|youtube|linkedin/i.test(l.h))""")
        seen=set()
        for l in links[:30]:
            if l["h"] in seen: continue
            seen.add(l["h"])
            print("   ", l["t"].encode("ascii","replace").decode()[:50], "=>", l["h"][:120])
        body = await page.evaluate("document.body.innerText")
        print("\nBODY:", body[:1200])
        await ctx.close()

asyncio.run(main())
