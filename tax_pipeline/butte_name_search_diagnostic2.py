"""
Check if doc search vs name search differ on login requirement.
"""
import sys
sys.path.insert(0, "..")
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG

cfg = RECORDER_CONFIG["butte"]
disclaimer_sel = cfg["disclaimer_selector"]

def accept_disclaimer(page):
    if page.query_selector(disclaimer_sel):
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)

    # Check doc search page
    print("=== DOC SEARCH PAGE (DOCSEARCH481S2) ===")
    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S2" not in page.url:
        page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    body = page.evaluate("() => document.body ? document.body.innerText : ''")
    has_login = "log in" in body.lower()
    print(f"  URL: {page.url}")
    print(f"  Has 'log in': {has_login}")

    # Find search button
    btns = page.query_selector_all("#searchButton")
    print(f"  #searchButton count: {len(btns)}")
    for b in btns:
        tag = b.evaluate("el => el.tagName")
        href = b.evaluate("el => el.href || ''")
        onclick = b.evaluate("el => el.getAttribute('onclick') || ''")
        print(f"    <{tag}> href={href} onclick={onclick}")

    # Check the form action
    forms = page.query_selector_all("form")
    print(f"  forms: {len(forms)}")
    for f in forms:
        action = f.evaluate("el => el.action || ''")
        method = f.evaluate("el => el.method || ''")
        print(f"    action={action} method={method}")

    # Check name search page
    print("\n=== NAME SEARCH PAGE (DOCSEARCH481S1) ===")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S1" not in page.url:
        page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    body = page.evaluate("() => document.body ? document.body.innerText : ''")
    has_login = "log in" in body.lower()
    print(f"  URL: {page.url}")
    print(f"  Has 'log in': {has_login}")

    btns = page.query_selector_all("#searchButton")
    print(f"  #searchButton count: {len(btns)}")
    for b in btns:
        tag = b.evaluate("el => el.tagName")
        href = b.evaluate("el => el.href || ''")
        onclick = b.evaluate("el => el.getAttribute('onclick') || ''")
        print(f"    <{tag}> href={href} onclick={onclick}")

    forms = page.query_selector_all("form")
    print(f"  forms: {len(forms)}")
    for f in forms:
        action = f.evaluate("el => el.action || ''")
        method = f.evaluate("el => el.method || ''")
        print(f"    action={action} method={method}")

    # Try clicking search button and check what happens via network
    print("\n  Attempting name search with network monitoring...")
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SMITH")

    # Check what the button actually does
    btn = page.query_selector("#searchButton")
    btn_html = btn.evaluate("el => el.outerHTML") if btn else "NONE"
    print(f"  Button HTML: {btn_html}")

    # Also check if there's a form that wraps the search
    form_html = page.evaluate("""() => {
        const input = document.querySelector('#field_BothNamesID');
        if (input) {
            const form = input.closest('form');
            if (form) return form.outerHTML.substring(0, 1000);
            return 'No form wrapper found';
        }
        return 'No #field_BothNamesID found';
    }""")
    print(f"  Form wrapper: {form_html[:500]}")

    # Try submitting via form submit instead of button click
    print("\n  Trying form.requestSubmit()...")
    page.fill(cfg["search_field"], "SMITH")
    page.evaluate("() => { const form = document.querySelector('#field_BothNamesID').closest('form'); if(form) form.requestSubmit(); }")
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    print(f"  URL after submit: {page.url}")
    results = page.query_selector_all(cfg["results_selector"])
    print(f"  Results: {len(results)}")
    if not results:
        results2 = page.query_selector_all("li.ss-search-row")
        print(f"  li.ss-search-row: {len(results2)}")
        body2 = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1000) : ''")
        print(f"  Body: {body2[:500]}")

    browser.close()
    print("\nDONE")
