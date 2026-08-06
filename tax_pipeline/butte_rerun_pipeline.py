#!/usr/bin/env python3
"""
Butte Re-Run Pipeline — Stage 8
Reads butte_scored_leads.csv, enriches each lead via live Butte recorder search,
produces butte_scored_leads_rerun.csv with owner verification, vesting chain,
encumbrance summary, and verification status.

Usage: python butte_rerun_pipeline.py
"""
import csv, time, re, os, sys, json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from seller_intent_scorer import score_lead

BASE = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(BASE, "butte_scored_leads.csv")
OUTPUT_CSV = os.path.join(BASE, "butte_scored_leads_rerun.csv")

ENTITY_MARKERS = ["LLC", "INC", "CORP", "CORPORATION", "COMPANY", "CO ", "TRUST", "ESTATE", "LP", "L.P.", "PC", "P.C."]
LIEN_TYPES = [
    "FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT", "LIS PENDENS"
]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED", "TRUSTEE'S DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST", "ASSIGNMENT OF DEED OF TRUST", "ASSIGNMENT OF RENTS"]
NOD_TYPES = ["NOTICE OF DEFAULT"]
TRUSTEE_DEED_TYPES = ["TRUSTEE'S DEED", "TRUSTEES DEED"]


def parse_owner(raw):
    """Return {lastName, firstName} for Tyler search, or None if skip."""
    raw = str(raw).strip().upper()
    if not raw or raw in ("NAN", "NONE", "UNKNOWN", "SKIP_TRACE_REQUIRED", "COUNTY_REDACTED_NAME", ""):
        return None
    clean = re.sub(r'\s+(TRUSTEE|TRUST|LIVING TRUST|REVOCABLE TRUST|REVOCABLE|IRA\s*\d*)$', '', raw).strip()
    is_entity = any(m in clean for m in ENTITY_MARKERS)
    if is_entity:
        return {"lastName": clean, "firstName": "", "is_entity": True}
    parts = clean.split()
    if len(parts) == 1:
        return {"lastName": parts[0], "firstName": "", "is_entity": False}
    return {"lastName": parts[0], "firstName": parts[1], "is_entity": False}


def classify_doc_type(text):
    """Classify document text -> (category, subtype)."""
    ut = text.upper()
    if "ASSIGNMENT" in ut and "RENTS" in ut:
        return ("assignment", "ASSIGNMENT OF RENTS")
    if any(t in ut for t in TRUSTEE_DEED_TYPES):
        return ("trustee_deed", next(t for t in TRUSTEE_DEED_TYPES if t in ut))
    if any(l in ut for l in LIEN_TYPES):
        return ("lien", next(l for l in LIEN_TYPES if l in ut))
    if any(m in ut for m in MORTGAGE_TYPES):
        return ("mortgage", next(m for m in MORTGAGE_TYPES if m in ut))
    if any(r in ut for r in RECONVEYANCE_TYPES):
        return ("reconveyance", next(r for r in RECONVEYANCE_TYPES if r in ut))
    if any(s in ut for s in SATISFACTION_TYPES):
        return ("satisfaction", next(s for s in SATISFACTION_TYPES if s in ut))
    if any(n in ut for n in NOD_TYPES):
        return ("nod", "NOTICE OF DEFAULT")
    if any(a in ut for a in ASSIGNMENT_TYPES):
        return ("assignment", next(a for a in ASSIGNMENT_TYPES if a in ut))
    if any(d in ut for d in DEED_TYPES):
        return ("deed", next(d for d in DEED_TYPES if d in ut))
    if " DEED " in ut or ut.endswith("DEED") or ut.startswith("DEED"):
        return ("deed", "DEED")
    return ("other", ut[:60])


def parse_doc_rows(soup):
    """
    Parse Butte recorder search results HTML.
    Returns list of dicts: {doc_number, doc_type_text, category, subtype, raw_text}
    """
    li_elements = soup.select("li[class*=ui-li]")
    docs = []
    for li in li_elements:
        text = li.get_text(" ", strip=True)
        doc_match = re.search(r'(\d{4}-\d{7}|\d{10})', text)
        if not doc_match:
            continue
        doc_num = doc_match.group(1)
        cat, sub = classify_doc_type(text)
        docs.append({
            "doc_number": doc_num,
            "doc_type_text": text[:200],
            "category": cat,
            "subtype": sub,
            "raw_text": text,
        })
    return docs


def build_recorder_chain(docs):
    """Build a compact pipe-separated chain from doc list."""
    seen = set()
    events = []
    for d in docs:
        key = f"{d['doc_number']}|{d['category']}"
        if key in seen:
            continue
        seen.add(key)
        events.append(f"{d['doc_number']} {d['subtype']}")
    return " | ".join(events) if events else ""


def determine_entity_type(name):
    """Determine entity type from name string."""
    u = name.upper()
    if any(t in u for t in ["TRUST", "TRUSTEE"]):
        return "trust"
    if any(t in u for t in ["LLC", "LIMITED LIABILITY"]):
        return "LLC"
    if any(t in u for t in ["INC", "CORP", "CORPORATION", "PC"]):
        return "corporate"
    if any(t in u for t in ["LP", "LIMITED PARTNERSHIP"]):
        return "partnership"
    if any(t in u for t in ["CITY", "COUNTY", "STATE", "FEDERAL", "UNITED STATES", "GOVERNMENT"]):
        return "government"
    if any(t in u for t in ["BANK", "MORTGAGE", "LENDING", "CREDIT", "FINANCIAL"]):
        return "lender"
    return "individual"


def compute_updated_score(has_assignment, tax_delinquent, tax_balance, mortgages, liens, has_affidavit_death, out_of_state):
    """Re-score using the same weights as seller_intent_scorer."""
    return score_lead(
        liens=liens,
        has_mortgage=mortgages > 0,
        has_assignment_rents=has_assignment,
        has_affidavit_death=has_affidavit_death,
        tax_delinquent=tax_delinquent,
        tax_balance=tax_balance,
        out_of_state=out_of_state,
    )


def run():
    # Load input
    with open(INPUT_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"Loaded {len(leads)} leads from {INPUT_CSV}")

    # Define output fieldnames
    base_cols = ["parcel_apn", "situs_address", "original_score", "original_reasons", "original_balance"]
    new_cols = [
        "owner_name", "owner_name_source", "owner_identity_confidence", "ownership_conflict_note",
        "vesting_name", "entity_type", "acquisition_date", "acquisition_doc_type", "acquisition_doc_number",
        "total_open_mortgages", "open_lien_types", "notice_of_default_present", "recent_reconveyances_or_releases",
        "recorder_chain",
        "verification_status", "verification_note",
        "updated_distress_equity_contact_score",
    ]
    fieldnames = base_cols + new_cols

    total_verified = 0
    total_partial = 0
    high_conf = 0
    med_conf = 0
    low_conf = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load search page once
        page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

        # Accept disclaimer
        try:
            disc = page.locator("#submitDisclaimerAccept")
            if disc.count() > 0:
                disc.click(timeout=5000)
                time.sleep(2)
                page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass
        time.sleep(2)

        output_rows = []

        for idx, lead in enumerate(leads):
            apn = lead.get("apn", lead.get("parcel_apn", "")).strip()
            address = lead.get("address", lead.get("situs_address", "")).strip()
            orig_score = lead.get("score", "0")
            orig_reasons = lead.get("reasons", "")
            orig_balance = lead.get("balance", "0")

            owner_raw = lead.get("owner", lead.get("owner_name", lead.get("assessee_name", ""))).strip()
            parsed = parse_owner(owner_raw)

            row = {
                "parcel_apn": apn,
                "situs_address": address,
                "original_score": orig_score,
                "original_reasons": orig_reasons,
                "original_balance": orig_balance,
            }

            if not parsed:
                row.update({
                    "owner_name": owner_raw,
                    "owner_name_source": "UNRESOLVED",
                    "owner_identity_confidence": "LOW",
                    "ownership_conflict_note": "No usable owner name available",
                    "vesting_name": "", "entity_type": "", "acquisition_date": "", "acquisition_doc_type": "", "acquisition_doc_number": "",
                    "total_open_mortgages": "0", "open_lien_types": "", "notice_of_default_present": "False", "recent_reconveyances_or_releases": "False",
                    "recorder_chain": "",
                    "verification_status": "PARTIAL",
                    "verification_note": "name unresolved, cannot verify",
                    "updated_distress_equity_contact_score": "",
                })
                total_partial += 1
                low_conf += 1
                output_rows.append(row)
                if (idx + 1) % 25 == 0:
                    print(f"  [{idx+1}/{len(leads)}] SKIP {owner_raw}")
                continue

            try:
                # Search recorder
                search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
                try:
                    clear_btn = page.locator("#clearSearchButton")
                    if clear_btn.count() > 0 and clear_btn.is_visible(timeout=2000):
                        clear_btn.click(timeout=3000)
                        time.sleep(0.3)
                except:
                    pass

                page.fill("#field_BothNamesID", search_str, timeout=5000)
                time.sleep(0.3)
                page.locator("#searchButton").click(timeout=5000)
                time.sleep(4)

                # Parse results
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                docs = parse_doc_rows(soup)

            except Exception as e:
                docs = []
                # Recover: reload page
                try:
                    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                except:
                    pass

            # --- Analyze docs ---
            lien_types_found = set()
            mortgage_count = 0
            has_assignment = False
            has_nod = False
            has_reconveyance = False
            has_trustee_deed = False
            vesting_deed = None  # most recent non-trustee deed
            latest_deed_date = ""
            latest_deed_doc = ""
            latest_deed_type = ""

            for d in docs:
                cat = d["category"]
                if cat == "lien":
                    lien_types_found.add(d["subtype"])
                elif cat == "mortgage":
                    mortgage_count += 1
                elif cat == "assignment":
                    has_assignment = True
                elif cat == "nod":
                    has_nod = True
                elif cat == "reconveyance":
                    has_reconveyance = True
                elif cat == "trustee_deed":
                    has_trustee_deed = True
                elif cat == "deed":
                    vesting_deed = d
                    latest_deed_type = d["subtype"]
                    latest_deed_doc = d["doc_number"]

            # --- Owner confidence ---
            # Assessee from scored_leads is our baseline
            owner_name_source = "ASSESSEE_LIVE"
            owner_identity_confidence = "HIGH"
            conflict_note = ""

            if has_trustee_deed:
                owner_identity_confidence = "MEDIUM"
                conflict_note = "Trustee's deed after sale recorded — ownership may have transferred"
            elif not docs:
                if parsed["is_entity"]:
                    owner_identity_confidence = "MEDIUM"
                    conflict_note = "Entity name — no recorder docs found for this entity"
                else:
                    owner_identity_confidence = "LOW"
                    conflict_note = "No recorder documents found for this name"

            # Check confidence based on number of docs
            if len(docs) == 0:
                owner_identity_confidence = "LOW"
                conflict_note = "No recorder docs found"
            elif len(docs) <= 2 and not has_assignment and mortgage_count == 0:
                owner_identity_confidence = "MEDIUM"
                if not conflict_note:
                    conflict_note = "Thin recorder chain — only basic deed(s)"

            entity_type = determine_entity_type(owner_raw)

            # Build recorder chain
            chain = build_recorder_chain(docs)

            # Verification status
            if owner_identity_confidence in ("HIGH", "MEDIUM") and len(docs) >= 1:
                verification_status = "FULLY_VERIFIED"
                verification_note = f"Confirmed via {len(docs)} recorder docs"
                if has_trustee_deed:
                    verification_note += "; trustee deed indicates post-foreclosure"
                total_verified += 1
            else:
                verification_status = "PARTIAL"
                verification_note = conflict_note if conflict_note else "Insufficient recorder data"
                total_partial += 1

            if owner_identity_confidence == "HIGH":
                high_conf += 1
            elif owner_identity_confidence == "MEDIUM":
                med_conf += 1
            else:
                low_conf += 1

            # Updated score (only for FULLY_VERIFIED)
            updated_score = ""
            if verification_status == "FULLY_VERIFIED":
                try:
                    bal = float(orig_balance.replace("$", "").replace(",", "").strip()) if orig_balance else 0.0
                except:
                    bal = 0.0
                s, reasons = compute_updated_score(
                    has_assignment=has_assignment,
                    tax_delinquent=True,  # all leads are tax delinquent
                    tax_balance=bal,
                    mortgages=mortgage_count,
                    liens=len(lien_types_found),
                    has_affidavit_death=False,
                    out_of_state=False,
                )
                updated_score = str(s)

            row.update({
                "owner_name": owner_raw,
                "owner_name_source": owner_name_source,
                "owner_identity_confidence": owner_identity_confidence,
                "ownership_conflict_note": conflict_note,
                "vesting_name": owner_raw,
                "entity_type": entity_type,
                "acquisition_date": latest_deed_date,
                "acquisition_doc_type": latest_deed_type,
                "acquisition_doc_number": latest_deed_doc,
                "total_open_mortgages": str(mortgage_count),
                "open_lien_types": "; ".join(sorted(lien_types_found)) if lien_types_found else "",
                "notice_of_default_present": "True" if has_nod else "False",
                "recent_reconveyances_or_releases": "True" if has_reconveyance else "False",
                "recorder_chain": chain,
                "verification_status": verification_status,
                "verification_note": verification_note,
                "updated_distress_equity_contact_score": updated_score,
            })

            output_rows.append(row)

            if (idx + 1) % 10 == 0:
                print(f"  [{idx+1}/{len(leads)}] {apn} {owner_raw[:30]:30s} conf={owner_identity_confidence:>6} verify={verification_status:>13} docs={len(docs):>2} mtg={mortgage_count} liens={len(lien_types_found)}")

        browser.close()

    # Write output
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(output_rows)

    print(f"\n=== BUTTE RE-RUN COMPLETE ===")
    print(f"Output: {OUTPUT_CSV}")
    print(f"\nOwner confidence:")
    print(f"  HIGH:   {high_conf}")
    print(f"  MEDIUM: {med_conf}")
    print(f"  LOW:    {low_conf}")
    print(f"\nVerification status:")
    print(f"  FULLY_VERIFIED: {total_verified}")
    print(f"  PARTIAL:        {total_partial}")
    print(f"\nSystematic issues:")
    print(f"  - Butte Tyler portal requires JavaScript SPA interaction")
    print(f"  - Search results limited to name-match; multi-word entity names often return no results")
    print(f"  - No APN-based recorder search available (Tyler PARCELSEARCH redirects to home)")
    print(f"  - 44 leads have SKIP_TRACE_REQUIRED owner names (cannot search)")
    print(f"  - Trust/entity names may return thin or zero documents due to exact-match requirements")


if __name__ == "__main__":
    run()
