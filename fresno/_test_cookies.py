import asyncio, sys, json, re
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
import httpx
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

async def get_browser_cookies():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://fresnocountyca-web.tylerhost.net/web/user/disclaimer", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.evaluate(
            """() => { const f = Array.from(document.querySelectorAll('form')).find(f => (f.action||'').includes('/web/user/disclaimer')); if (f) f.submit(); }""")
        await page.wait_for_timeout(8000)
        cookies = await ctx.cookies()
        await ctx.close()
        return cookies

def run_http(cookies):
    jar = httpx.Cookies()
    for ck in cookies:
        jar.set(ck["name"], ck["value"], domain=ck["domain"])
    c = httpx.Client(base_url="https://fresnocountyca-web.tylerhost.net", timeout=25,
        headers={"User-Agent": UA}, follow_redirects=True, cookies=jar)
    c.get("/web/search/DOCSEARCH377S5")
    AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest",
            "accept": "application/json, text/javascript, */*; q=0.01",
            "referer": "https://fresnocountyca-web.tylerhost.net/web/search/DOCSEARCH377S5"}
    payload = {
        "field_ParcelID": "090-101-15",
        "field_selfservice_documentTypes-containsInput": "Contains Any",
        "field_selfservice_documentTypes": "",
    }
    c.post("/web/searchPost/DOCSEARCH377S5", data=payload, headers=AJAX)
    r3 = c.get("/web/searchResults/DOCSEARCH377S5", headers=AJAX, params={"page": 1, "_": "1785520255944"})
    t = re.sub(r"<[^>]+>", " ", r3.text)
    t = re.sub(r"\s+", " ", t)
    print("searchResults:", r3.status_code)
    print(t[:1500])

cookies = asyncio.run(get_browser_cookies())
print("Has disclaimerAccepted:", any(c["name"] == "disclaimerAccepted" for c in cookies))
run_http(cookies)
