import asyncio, os, sys
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True, user_agent=UA,
            viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = "https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=09/10/26"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        html = await page.content()
        out = os.path.join(r"C:\Users\chuck\Downloads\county_pipeline\fresno", "_auction_raw.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print("saved", len(html), "bytes to", out)
        # Search for item-related markers
        import re
        for marker in ["PreviewItems", "ItemsForSale", "zaction=item", "Zmethod=item", "itemid", "ItemID", "Search", "SearchButton", "AuctionDay", "dataitem", "listing"]:
            idx = html.lower().find(marker.lower())
            if idx >= 0:
                print("FOUND marker:", marker, "@", idx)
                print(html[max(0,idx-200):idx+300].replace("\n", " ")[:600])
                print("---")
        await ctx.close()

asyncio.run(main())
