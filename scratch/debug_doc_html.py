"""Debug the document search result HTML structure"""
from playwright.sync_api import sync_playwright
import time, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script("""
        const _orig = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (delay > 1000) delay = 100;
            return _orig(fn, delay, ...args);
        };
    """)
    
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(1)
    
    # Accept disclaimer
    for _ in range(20):
        try:
            a = page.locator('#submitDisclaimerAccept')
            if a.count() > 0 and a.is_visible(timeout=500):
                if not a.is_disabled():
                    a.click(timeout=3000)
                    time.sleep(2)
                    break
        except:
            pass
        time.sleep(0.5)
    
    # Enter doc number and search
    page.locator('#field_DocumentNumberID').fill('2017-0021298')
    page.keyboard.press('Enter')
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass
    time.sleep(3)
    
    # Get the result HTML structure
    result_html = page.evaluate("""
        () => {
            return document.body.innerHTML;
        }
    """)
    
    with open(os.path.join(base_dir, 'scratch/doc_result_full.html'), 'w') as f:
        f.write(result_html)
    
    print(f"Saved HTML ({len(result_html)} chars)")
    
    # Try to find grantor/grantee elements
    elements = page.evaluate("""
        () => {
            const results = [];
            // Look for all elements containing Grantor/Grantee
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text && (text.includes('Grantor') || text.includes('Grantee'))) {
                    results.push({
                        tag: el.tagName,
                        id: el.id,
                        class: el.className.substring(0, 60),
                        text: text.substring(0, 300)
                    });
                }
            }
            return results;
        }
    """)
    
    print(f"\n=== Elements containing Grantor/Grantee ({len(elements)}) ===")
    for el in elements:
        print(f"  <{el['tag']}> id={el['id'][:30]} class={el['class'][:40]}")
        print(f"    text: {el['text'][:200]}")
        print()
    
    # Try a different approach - get all table rows if present
    table_data = page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            const results = [];
            tables.forEach((t, i) => {
                const rows = t.querySelectorAll('tr');
                const rowData = [];
                rows.forEach(r => {
                    const cells = r.querySelectorAll('td, th');
                    rowData.push(Array.from(cells).map(c => c.innerText.trim()).join(' | '));
                });
                results.push({table: i, rows: rowData});
            });
            return results;
        }
    """)
    
    print(f"\n=== Tables ({len(table_data)}) ===")
    for t in table_data:
        print(f"  Table {t['table']}: {len(t['rows'])} rows")
        for r in t['rows'][:20]:
            print(f"    {r[:150]}")
    
    browser.close()
