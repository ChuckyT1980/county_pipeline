import os
import re
import time
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from classifier import classify

app = Flask(__name__)

LIEN_TYPES = ["FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
              "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
              "NOTICE OF DEFAULT", "LIS PENDENS"]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE",
                       "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "RELEASE OF LIEN",
                       "RELEASE OF FEDERAL TAX LIEN"]

def format_name(name):
    name = str(name).strip().upper()
    if not name or name in {"NAN", "NONE", "UNKNOWN"}:
        return None
    markers = ["LLC", "INC", "CORP", "TRUST", "TR", "REVOC", "ESTATE", "HOLDINGS"]
    if any(m in name.split() for m in markers):
        return {"lastName": name.replace(",", " ").strip(), "firstName": ""}
    if name.count(",") == 1:
        parts = [p.strip() for p in name.split(",")]
        first = parts[1].split()[0] if parts[1].split() else ""
        return {"lastName": parts[0], "firstName": first}
    tokens = name.replace(",", " ").split()
    if len(tokens) >= 2:
        return {"lastName": tokens[0], "firstName": tokens[1]}
    return {"lastName": name, "firstName": ""}

def ensure_search_ready(page):
    for attempt in range(3):
        try:
            if "disclaimer" in page.url.lower():
                try:
                    page.evaluate("""
                        const btn = document.getElementById('submitDisclaimerAccept');
                        if(btn) { btn.disabled = false; btn.click(); }
                    """)
                    page.wait_for_load_state("networkidle")
                    time.sleep(1)
                except Exception:
                    pass
            field = page.locator("#field_BothNamesID")
            if field.count() > 0 and field.is_visible(timeout=3000):
                return True
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return False

@app.route('/enrich', methods=['POST'])
def enrich():
    data = request.json
    if not data or 'owner_name' not in data:
        return jsonify({"error": "Missing owner_name"}), 400

    owner_name = data['owner_name']
    parsed = format_name(owner_name)
    if not parsed:
        return jsonify({"error": "Could not parse owner name"}), 400

    search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
    docs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("""
            const _orig = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                if (delay > 1000) delay = 100;
                return _orig(fn, delay, ...args);
            };
        """)

        try:
            page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1",
                       timeout=60000)
            page.wait_for_load_state("load", timeout=60000)

            if ensure_search_ready(page):
                try:
                    clear_btn = page.locator("#clearSearchButton")
                    if clear_btn.count() > 0 and clear_btn.is_visible(timeout=2000):
                        clear_btn.click()
                        time.sleep(0.5)
                except Exception:
                    pass

                page.fill("#field_BothNamesID", search_str, timeout=8000)
                time.sleep(0.5)
                page.click("#searchButton")
                time.sleep(4)

                try:
                    page.wait_for_selector(".ui-li-static", timeout=8000)
                except Exception:
                    pass

                ensure_search_ready(page)
                soup = BeautifulSoup(page.content(), "html.parser")

                for li in soup.find_all("li", class_="ui-li-static"):
                    text = li.text.strip().upper()
                    doc_num_match = re.search(r'(\d{10})', text)
                    doc_number = doc_num_match.group(1) if doc_num_match else ""

                    # Determine doc_type
                    doc_type = "OTHER"
                    for dt in DEED_TYPES:
                        if dt in text:
                            doc_type = "DEED"
                            break
                    if doc_type == "OTHER":
                        for mt in MORTGAGE_TYPES:
                            if mt in text:
                                doc_type = mt
                                break
                    if doc_type == "OTHER":
                        for rt in RECONVEYANCE_TYPES:
                            if rt in text:
                                doc_type = "RECONVEYANCE"
                                break
                    if doc_type == "OTHER":
                        if "NOTICE OF POWER TO SELL" in text:
                            doc_type = "NOTICE OF POWER TO SELL"
                        elif "AFFIDAVIT OF DEATH" in text:
                            doc_type = "AFFIDAVIT OF DEATH"
                        elif "ASSIGNMENT OF RENTS" in text:
                            doc_type = "ASSIGNMENT OF RENTS"
                        else:
                            for lt in LIEN_TYPES:
                                if lt in text:
                                    doc_type = lt
                                    break
                            for st in SATISFACTION_TYPES:
                                if st in text:
                                    doc_type = st
                                    break

                    # Extract grantor/grantee
                    grantor = ""
                    grantee = ""
                    if "GRANTOR:" in text:
                        grantor = text.split("GRANTOR:")[1].split("GRANTEE:")[0].strip()
                    if "GRANTEE:" in text:
                        grantee = text.split("GRANTEE:")[1].strip()

                    # Extract date (MM/DD/YYYY pattern)
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
                    recording_date = date_match.group(1) if date_match else ""

                    docs.append({
                        "doc_number": doc_number,
                        "doc_type": doc_type,
                        "grantor": grantor,
                        "grantee": grantee,
                        "recording_date": recording_date,
                        "raw_text": li.text.strip()[:200]
                    })
        finally:
            browser.close()

    flags = classify(docs, owner_name)

    return jsonify({
        "owner_name": owner_name,
        "search_str": search_str,
        "recorder_checked_at": time.time(),
        "recorder_docs_found": len(docs),
        **flags
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
