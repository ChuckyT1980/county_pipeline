import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating...")
        await page.goto("https://recordsearch.tehama.gov/web")
        
        try:
            await page.wait_for_selector("button#submitDisclaimerAccept", timeout=5000)
            await page.click("button#submitDisclaimerAccept")
            print("Accepted disclaimer.")
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            print("No disclaimer found or error:", e)
            
        print("Current URL:", page.url)
        
        print("Loading search query for SOTO JOSE...")
        await page.goto("https://recordsearch.tehama.gov/web?lastName=SOTO&firstName=JOSE")
        await page.wait_for_load_state("networkidle")
        
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # Find search button
        for a in soup.find_all("a"):
            if "search" in a.text.lower() and "btn" in a.get("class", []):
                print("Found A button:", a.get("id"), a.text.strip())
        for b in soup.find_all("button"):
            if "search" in b.text.lower():
                print("Found Button:", b.get("id"), b.text.strip())
                
        # Try to click the Search button (often id='searchButton' or similar)
        try:
            await page.click("a#searchButton", timeout=3000)
            print("Clicked a#searchButton")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000) # Give results time to load
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            # Look for result tables or list
            results = soup.find_all("ul", class_="ui-listview") or soup.find_all("table")
            print("Found result elements:", len(results))
            for tr in soup.find_all("li")[:10]:
                print(tr.text.strip()[:100])
        except Exception as e:
            print("Could not click search or parse results:", type(e))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
