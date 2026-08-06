import asyncio, os
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
OUT = r"C:\Users\chuck\Downloads\county_pipeline\fresno\downloaded_pdfs"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

URLS = {
    "june-13-2025-excess-proceeds-list.pdf": "https://www.fresnocountyca.gov/files/assets/county/v/1/auditor-controller-treasurer-tax-collector/tax-sale-amp-excess-proceeds/june-13-2025-excess-proceeds-list.pdf",
    "03-04.2025-excess-proceeds-claim-form.pdf": "https://www.fresnocountyca.gov/files/assets/county/v/1/auditor-controller-treasurer-tax-collector/tax-sale-amp-excess-proceeds/03-04.2025-excess-proceeds-claim-form.pdf",
}

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000},
            accept_downloads=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.fresnocountyca.gov", wait_until="domcontentloaded", timeout=60000)
        for name, url in URLS.items():
            try:
                async with page.expect_download(timeout=45000) as dl_info:
                    await page.evaluate(f"window.location.href = '{url}'")
                dl = await dl_info.value
                path = os.path.join(OUT, name)
                await dl.save_as(path)
                size = os.path.getsize(path)
                is_pdf = open(path, "rb").read(5) == b"%PDF-"
                print("OK" if is_pdf else "FAIL", name, size, "bytes, pdf=", is_pdf)
            except Exception as e:
                print("ERR", name, type(e).__name__, str(e)[:120])
        await ctx.close()

asyncio.run(main())
