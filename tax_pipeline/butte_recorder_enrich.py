#!/usr/bin/env python3
"""
Butte-Specific Recorder Enrichment — replaces generic Stage 7 for Butte.

Strategy: search Tyler portal by owner name, parse result <li> elements,
classify documents into liens, mortgages, assignments of rents, etc.

Usage: python butte_recorder_enrich.py
"""
import csv, time, re, os, sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "butte_MASTER_leads_with_liens.csv")

# Document classification — same as stage7
LIEN_TYPES = [
    "FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT", "LIS PENDENS"
]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST", "ASSIGNMENT OF DEED OF TRUST", "ASSIGNMENT OF RENTS"]


def parse_owner_name(raw):
    """Split owner name into last/first for Butte Tyler search."""
    raw = str(raw).strip().upper()
    if not raw or raw in ("NAN", "NONE", "UNKNOWN", "SKIP_TRACE_REQUIRED", "COUNTY_REDACTED_NAME"):
        return None
    # Remove trust/entity suffixes for broader search
    clean = re.sub(r'\s+(TRUSTEE|TRUST|LIVING TRUST|REVOCABLE TRUST|REVOCABLE|IRA\s*\d*)$', '', raw).strip()
    # For entity names, search the whole thing
    entity_markers = ["LLC", "INC", "CORP", "CORPORATION", "COMPANY", "CO ", "TRUST", "ESTATE", "LP", "L.P."]
    is_entity = any(m in clean for m in entity_markers)
    if is_entity:
        return {"lastName": clean, "firstName": ""}
    # Split into last/first for individual names
    parts = clean.split()
    if len(parts) == 1:
        return {"lastName": parts[0], "firstName": ""}
    elif len(parts) == 2:
        return {"lastName": parts[0], "firstName": parts[1]}
    else:
        return {"lastName": parts[0], "firstName": parts[1]}
        # Ignore middle names/initials


def classify_document(doc_text):
    """Classify a document text and return (type, sub_type)."""
    ut = doc_text.upper()
    if any(l in ut for l in LIEN_TYPES):
        return ("lien", next(l for l in LIEN_TYPES if l in ut))
    if any(m in ut for m in MORTGAGE_TYPES):
        return ("mortgage", next(m for m in MORTGAGE_TYPES if m in ut))
    if any(r in ut for r in RECONVEYANCE_TYPES):
        return ("reconveyance", next(r for r in RECONVEYANCE_TYPES if r in ut))
    if any(s in ut for s in SATISFACTION_TYPES):
        return ("satisfaction", next(s for s in SATISFACTION_TYPES if s in ut))
    if any(a in ut for a in ASSIGNMENT_TYPES):
        return ("assignment", next(a for a in ASSIGNMENT_TYPES if a in ut))
    if any(d in ut for d in DEED_TYPES):
        return ("deed", next(d for d in DEED_TYPES if d in ut))
    if " DEED " in ut or ut.endswith("DEED") or ut.startswith("DEED"):
        return ("deed", "DEED")
    return ("other", ut[:40])


def run():
    # Read CSV
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Track fields
    fieldnames = list(rows[0].keys())
    for col in ("active_liens", "mortgages", "has_assignment_of_rents",
                "has_affidavit_of_death", "ownership_status"):
        if col not in fieldnames:
            fieldnames.append(col)

    print(f"Searching {len(rows)} Butte leads by owner name...")

    total_liens = 0
    total_mortgages = 0
    total_assignments = 0
    total_searched = 0
    total_errors = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load search page
        page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=30000)

        # Accept disclaimer
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            disc = page.locator("#submitDisclaimerAccept")
            if disc.count() > 0:
                disc.click(timeout=5000)
                time.sleep(2)
                page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass
        time.sleep(2)

        for idx, row in enumerate(rows):
            owner = row.get("owner_name", row.get("assessee_name", "")).strip()
            parsed = parse_owner_name(owner)
            if not parsed:
                # Reset values for SKIP_TRACE owners
                row["active_liens"] = "0"
                row["mortgages"] = "0"
                row["has_assignment_of_rents"] = "False"
                row["has_affidavit_of_death"] = "False"
                row["ownership_status"] = "Current"
                if (idx + 1) % 25 == 0:
                    print(f"  [{idx+1}/{len(rows)}] skipped '{owner}'")
                continue

            total_searched += 1

            try:
                search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()

                # Clear previous search
                try:
                    clear_btn = page.locator("#clearSearchButton")
                    if clear_btn.count() > 0 and clear_btn.is_visible(timeout=2000):
                        clear_btn.click(timeout=3000)
                        time.sleep(0.5)
                except:
                    pass

                page.fill("#field_BothNamesID", search_str, timeout=5000)
                time.sleep(0.3)

                page.locator("#searchButton").click(timeout=5000)
                time.sleep(4)

                # Parse results
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Find all li elements that could be document rows
                li_elements = soup.select("li[class*=ui-li]")

                liens = 0
                mortgages = 0
                satisfactions = 0
                reconveyances = 0
                has_assignment = False
                has_affidavit_death = False
                ownership = "Current"
                found_docs = 0

                for li in li_elements:
                    text = li.get_text(" ", strip=True).upper()

                    # Skip non-document rows (no doc number)
                    if not re.search(r'\b\d{4}-\d{7}\b', text):
                        continue

                    found_docs += 1
                    ctype, subtype = classify_document(text)

                    if ctype == "lien":
                        liens += 1
                    elif ctype == "mortgage":
                        mortgages += 1
                    elif ctype == "reconveyance":
                        reconveyances += 1
                    elif ctype == "satisfaction":
                        satisfactions += 1
                    elif ctype == "assignment":
                        has_assignment = True
                    elif ctype == "deed":
                        # Check if grantor/grantee indicates transfer
                        if "GRANTOR:" in text and parsed['lastName'] in text.split("GRANTOR:")[1][:100]:
                            if "GRANTEE:" in text:
                                grantee = text.split("GRANTEE:")[1][:100]
                                if parsed['lastName'] in grantee or parsed['firstName'] in grantee:
                                    ownership = "Possible Transfer"
                                else:
                                    ownership = "Sold / Transfer Detected"
                            else:
                                ownership = "Sold / Transfer Detected"

                # Store results
                active = max(0, liens - satisfactions)
                net_mortgages = max(0, mortgages - reconveyances)
                row["active_liens"] = str(active)
                row["mortgages"] = str(net_mortgages)
                row["has_assignment_of_rents"] = str(has_assignment)
                row["has_affidavit_of_death"] = str(has_affidavit_death)
                row["ownership_status"] = ownership

                total_liens += active
                total_mortgages += net_mortgages
                if has_assignment:
                    total_assignments += 1

                if (idx + 1) % 10 == 0:
                    print(f"  [{idx+1}/{len(rows)}] {search_str[:35]:35s} docs={found_docs} liens={active} mtg={net_mortgages} asgn={has_assignment}")

            except Exception as e:
                total_errors += 1
                row["active_liens"] = "0"
                row["mortgages"] = "0"
                row["has_assignment_of_rents"] = "False"
                row["has_affidavit_of_death"] = "False"
                row["ownership_status"] = "Current"
                if (idx + 1) % 10 == 0:
                    print(f"  [{idx+1}/{len(rows)}] ERROR: {e}")

        browser.close()

    # Write CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\nDone! Searched {total_searched} names, {total_errors} errors")
    print(f"  Liens: {total_liens}, Mortgages: {total_mortgages}, Assignments: {total_assignments}")


if __name__ == "__main__":
    run()
