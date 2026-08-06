"""Quick test: JS click for doc search."""
import sys; sys.path.insert(0, '..')
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG
cfg = RECORDER_CONFIG['butte']
disclaimer_sel = cfg['disclaimer_selector']
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)
    page.goto(cfg['doc_search_url'], wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(2000)
    if page.query_selector(disclaimer_sel):
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state('networkidle')
    if 'DOCSEARCH' not in page.url:
        page.goto(cfg['doc_search_url'], wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(2000)
    page.wait_for_selector(cfg['doc_search_field'], timeout=10000)
    page.fill(cfg['doc_search_field'], '2024-0030607')
    page.evaluate('() => document.querySelector("#searchButton").click()')
    page.wait_for_timeout(5000)
    page.wait_for_load_state('networkidle')
    url = page.url
    res = page.query_selector_all(cfg['results_selector'])
    print(f'Doc search via JS click: URL={url}, Results={len(res)}')
    browser.close()
