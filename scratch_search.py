from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup
import urllib.parse
import json

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="tax_pipeline/eagleweb_state.json")
        page = context.new_page()
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1")
        time.sleep(2)
        
        page.fill("#field_BothNamesID", "TOERPE MATTHEW")
        page.click("#searchButton")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        results = soup.find_all("li", class_="ui-li-static")
        for li in results:
            print(li.text.strip())
            print("---")
        browser.close()

if __name__ == "__main__":
    run()
