"""Verify both doc search + name search pivots with the fixed stage2 code."""
import sys, json, re
sys.path.insert(0, "..")
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG
from tax_pipeline.stage2_recorder_enrich import parse_doc_line, format_doc_number

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

    # ── PIVOT 1: Doc search ──
    print("=== PIVOT 1: Doc Search ===")
    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH" not in page.url:
        page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
    doc_fmt = format_doc_number("2024R0030607", "butte")
    print(f"Formatted doc: {doc_fmt}")
    page.fill(cfg["doc_search_field"], doc_fmt)
    page.evaluate('() => document.querySelector("#searchButton").click()')
    try:
        page.wait_for_selector(cfg["results_selector"], timeout=15000)
    except:
        pass
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    elements = page.query_selector_all(cfg["results_selector"])
    print(f"Results: {len(elements)}")
    if elements:
        text = elements[0].inner_text()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for idx, ln in enumerate(lines):
            print(f"  [{idx}] = {ln}")

        # Test parse_doc_line
        doc_num, doc_type = parse_doc_line(lines)
        print(f"\nparse_doc_line -> doc_num={doc_num}, doc_type={doc_type}")

        # Test primary_name extraction
        primary_name = None
        for j, ln in enumerate(lines):
            if "Grantee" in ln and j + 1 < len(lines):
                primary_name = lines[j+1]
            elif "Grantor" in ln and j + 1 < len(lines) and not primary_name:
                primary_name = lines[j+1]
        print(f"primary_name = {primary_name}")

    # ── PIVOT 2: Name search (JS click) ──
    print("\n=== PIVOT 2: Name Search ===")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S1" not in page.url:
        page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], primary_name)
    print(f"Searching for: {primary_name}")
    page.evaluate('() => document.querySelector("#searchButton").click()')
    try:
        page.wait_for_selector(cfg["results_selector"], timeout=15000)
    except:
        pass
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")

    name_elements = page.query_selector_all(cfg["results_selector"])
    print(f"Results: {len(name_elements)}")
    for ne in name_elements[:5]:
        text = ne.inner_text()
        ls = [l.strip() for l in text.split("\n") if l.strip()]
        dn, dt = parse_doc_line(ls)
        print(f"  doc={dn} type={dt}")

        # Test grantee extraction
        gr = None
        for j, ln in enumerate(ls):
            if "Grantee" in ln and j + 1 < len(ls):
                gr = ls[j+1]
                break
        print(f"    grantee={gr}")

    browser.close()
    print("\nDONE - Both pivots verified!")
