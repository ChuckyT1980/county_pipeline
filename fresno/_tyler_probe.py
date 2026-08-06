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

        await page.goto("https://fresnocountyca-web.tylerhost.net/web/user/disclaimer", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        sub = await page.evaluate(
            """() => { const f = Array.from(document.querySelectorAll('form')).find(f => (f.action||'').includes('/web/user/disclaimer')); if (f) { f.submit(); return 'submitted'; } return 'no form'; }""")
        print("FORM:", sub)
        await page.wait_for_timeout(10000)
        print("after submit URL:", page.url)

        await page.goto("https://fresnocountyca-web.tylerhost.net/web/", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        print("HOME URL:", page.url)
        links = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]')).map(a=>({t:a.innerText.trim(),h:a.href}))
               .filter(l=>/search/i.test(l.h+' '+l.t))""")
        for l in links[:12]:
            print("  LINK:", l["t"].encode("ascii","replace").decode()[:50], "=>", l["h"][:130])
        if links:
            href = links[0]["h"]
            await page.goto(href, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(4000)
            print("\nAfter navigate:", page.url)
            html = await page.content()
            print("DOCSEARCH IDs:", sorted(set(re.findall(r'DOCSEARCH\w+', html)))[:20])
            links2 = await page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]')).map(a=>({t:a.innerText.trim(),h:a.href}))
                   .filter(l=>l.h && /search|DOC/i.test(l.h+' '+l.t))""")
            for l in links2[:25]:
                print("   LINK:", l["t"].encode("ascii","replace").decode()[:45], "=>", l["h"][:130])
        await ctx.close()

asyncio.run(main())
