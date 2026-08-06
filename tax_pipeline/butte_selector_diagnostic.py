"""
Butte Recorder Selector Diagnostic
Launches Playwright, accepts the disclaimer, navigates to the search pages,
and dumps ALL input/button/textarea elements with their IDs, names, classes, and types.
This reveals the actual selectors that exist on Butte's Tyler portal.
"""
import json, time
from playwright.sync_api import sync_playwright

BASE = "https://recorder.buttecounty.net/web"
NAME_SEARCH = BASE + "/search/DOCSEARCH481S1"
DOC_SEARCH = BASE + "/search/DOCSEARCH481S2"

def dump_elements(page, label):
    """Extract all interactive elements from the current page."""
    elements = page.evaluate("""() => {
        const results = [];
        // All inputs, textareas, buttons, selects
        const selectors = 'input, textarea, button, select, a[data-role="button"]';
        document.querySelectorAll(selectors).forEach(el => {
            results.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                name: el.name || '',
                type: el.type || '',
                class: el.className || '',
                value: el.value || '',
                placeholder: el.placeholder || '',
                text: (el.textContent || '').trim().substring(0, 80),
                visible: el.offsetParent !== null,
                data_role: el.getAttribute('data-role') || '',
            });
        });
        // Also check for labels with "for" attribute
        document.querySelectorAll('label').forEach(el => {
            results.push({
                tag: 'label',
                id: el.id || '',
                name: '',
                type: 'label',
                class: el.className || '',
                value: '',
                placeholder: '',
                text: (el.textContent || '').trim().substring(0, 80),
                visible: el.offsetParent !== null,
                data_role: '',
                for_attr: el.getAttribute('for') || '',
            });
        });
        return results;
    }""")
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  URL: {page.url}")
    print(f"  Elements found: {len(elements)}")
    print(f"{'='*60}")
    for el in elements:
        if el.get('tag') == 'label':
            print(f"  <label for=\"{el['for_attr']}\" id=\"{el['id']}\"> {el['text'][:60]}")
        else:
            vis = "VISIBLE" if el['visible'] else "hidden"
            print(f"  <{el['tag']} id=\"{el['id']}\" name=\"{el['name']}\" type=\"{el['type']}\" "
                  f"class=\"{el['class'][:50]}\" data-role=\"{el['data_role']}\" [{vis}]> "
                  f"text=\"{el['text'][:40]}\" value=\"{el['value'][:40]}\"")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False so you can watch
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        page.set_default_timeout(15000)

        # ── Step 1: Go to name search page (will show disclaimer first) ──
        print(f"\nNavigating to: {NAME_SEARCH}")
        page.goto(NAME_SEARCH, wait_until="networkidle")
        time.sleep(2)
        dump_elements(page, "STEP 1: Initial load (likely disclaimer page)")

        # ── Step 2: Accept disclaimer ──
        print("\nLooking for disclaimer accept button...")
        btn = page.query_selector('#submitDisclaimerAccept')
        if not btn:
            btn = page.query_selector('button:has-text("I Accept")')
        if btn:
            print("  Found disclaimer button, clicking...")
            btn.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")
            print(f"  After disclaimer click, URL: {page.url}")
        else:
            print("  No disclaimer button found — maybe already accepted?")

        # ── Step 3: Navigate to name search ──
        print(f"\nNavigating to name search: {NAME_SEARCH}")
        page.goto(NAME_SEARCH, wait_until="networkidle")
        time.sleep(3)
        dump_elements(page, "STEP 2: Name search page (after disclaimer)")

        # ── Step 4: Try to dump full page HTML for the form area ──
        form_html = page.evaluate("""() => {
            const content = document.querySelector('[data-role="content"]') || document.querySelector('.ss-content') || document.body;
            return content ? content.innerHTML.substring(0, 5000) : 'NO CONTENT DIV FOUND';
        }""")
        print(f"\n{'='*60}")
        print("  STEP 3: Content area HTML (first 5000 chars)")
        print(f"{'='*60}")
        print(form_html[:5000])

        # ── Step 5: Navigate to doc search ──
        print(f"\nNavigating to doc search: {DOC_SEARCH}")
        page.goto(DOC_SEARCH, wait_until="networkidle")
        time.sleep(3)
        dump_elements(page, "STEP 4: Document search page")

        # ── Step 6: Also try the home page ──
        home = BASE + "/"
        print(f"\nNavigating to home: {home}")
        page.goto(home, wait_until="networkidle")
        time.sleep(2)
        dump_elements(page, "STEP 5: Home page")

        browser.close()
        print("\n\nDone. Check the output above for the actual field IDs.")

if __name__ == "__main__":
    main()
