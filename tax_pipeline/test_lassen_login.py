from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://eagleweb.co.lassen.ca.us/eweb/web/loginPOST.jsp?guest=true", timeout=60000)
    page.wait_for_load_state("networkidle")
    print("URL after login:", page.url)
    print("Title:", page.title())
    time.sleep(3)
    html = page.content()
    with open("lassen_debug.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved lassen_debug.html")
    browser.close()
