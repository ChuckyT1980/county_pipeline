#!/usr/bin/env python3
"""
Butte Auction Enrichment v2 — Two-step: doc_number -> grantee -> name search -> score
Targets 89 auction parcels not already in our scored leads.
"""
import csv, time, re, os, json
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(BASE, "..", "archive")
IDX_CSV = os.path.join(ARCHIVE, "tax_pipeline", "butte_AUTHORITATIVE_master_index.csv")
OUTPUT_CSV = os.path.join(BASE, "butte_auction_enriched.csv")

ENTITY_MARKERS = ["LLC","INC","CORP","CORPORATION","COMPANY","CO ","TRUST","ESTATE","LP","L.P.","PC","P.C."]
LIEN_TYPES = ["FEDERAL TAX LIEN","STATE TAX LIEN","ABSTRACT OF JUDGMENT","MECHANIC'S LIEN","MECHANICS LIEN","NOTICE OF DELINQUENT ASSESSMENT","NOTICE OF DEFAULT","LIS PENDENS"]
MORTGAGE_TYPES = ["DEED OF TRUST","MORTGAGE"]
DEED_TYPES = ["GRANT DEED","QUITCLAIM DEED","WARRANTY DEED","CORPORATION GRANT DEED","TRUSTEE'S DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE","FULL RECONVEYANCE","SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT","RELEASE OF LIEN","RELEASE OF FEDERAL TAX LIEN"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST","ASSIGNMENT OF DEED OF TRUST","ASSIGNMENT OF RENTS"]
NOD_TYPES = ["NOTICE OF DEFAULT"]
TRUSTEE_DEED_TYPES = ["TRUSTEE'S DEED","TRUSTEES DEED"]

AUCTION_APNS = [
    "022-210-078-000","026-111-008-000","027-120-038-000","027-290-021-000",
    "031-243-024-000","031-281-137-000","033-232-003-000","033-232-022-000",
    "033-232-025-000","033-232-026-000","035-073-020-000","041-260-027-000",
    "050-040-132-000","050-120-121-000","051-072-071-000","051-083-079-000",
    "051-171-067-000","051-280-005-000","052-011-094-000","052-031-040-000",
    "052-040-067-000","052-080-054-000","052-250-052-000","053-021-067-000",
    "053-180-086-000","054-161-037-000","054-192-095-000","054-260-006-000",
    "055-130-089-000","055-330-017-000","055-520-085-000","056-400-019-000",
    "058-260-060-000","058-330-038-000","058-330-046-000","058-370-023-000",
    "058-370-027-000","058-370-048-000","058-410-029-000","058-430-019-000",
    "059-087-011-000","059-087-017-000","059-092-008-000","061-550-017-000",
    "061-550-018-000","061-590-007-000","061-590-009-000","061-610-005-000",
    "061-610-009-000","062-140-027-000","062-190-025-000","062-190-029-000",
    "062-300-005-000","062-300-006-000","062-300-007-000","062-300-033-000",
    "062-300-044-000","062-300-077-000","062-300-078-000","062-310-012-000",
    "062-320-006-000","062-320-008-000","062-320-018-000","062-320-029-000",
    "062-340-018-000","062-350-024-000","062-690-027-000","062-710-019-000",
    "062-730-008-000","062-750-036-000","065-210-023-000","066-050-011-000",
    "066-100-010-000","066-130-036-000","066-220-001-000","066-230-047-000",
    "066-270-036-000","069-190-021-000","071-060-021-000","071-060-025-000",
    "071-150-003-000","071-240-025-000","071-270-029-000","071-270-045-000",
    "071-280-038-000","071-320-003-000","071-470-021-000","072-190-015-000",
    "072-200-034-000",
]

def recorder_format(doc_number):
    if not doc_number or len(doc_number) < 6:
        return None
    return doc_number[:4] + "-" + doc_number[5:]

def fetch_asrprint(apn):
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36","Referer": "https://common1.mptsweb.com/mbap/butte/asr"})
    try:
        r = s.get("https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/%s" % apn, timeout=15)
        if r.status_code != 200:
            return (apn, None, None, r.status_code)
        soup = BeautifulSoup(r.text, "html.parser")
        doc_number = None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td","th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label and value:
                    doc_number = value.strip()
                    break
        return (apn, doc_number, r.text[:500], 200)
    except Exception as e:
        return (apn, None, str(e), 0)

def batch_asrprint(padded_apns):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        fut = {ex.submit(fetch_asrprint, a): a for a in padded_apns}
        for f in concurrent.futures.as_completed(fut):
            apn, doc, text, status = f.result()
            results[apn] = {"doc_number": doc, "text": text, "status": status}
    return results

def grantee_from_recorder(page, doc_num):
    """Search recorder by doc number, extract Grantee name. Returns (grantee, full_text)."""
    doc_field = page.locator("#field_DocumentNumberID")
    search_btn = page.locator("#searchButton")
    try:
        doc_field.fill(doc_num, timeout=5000)
        time.sleep(0.3)
        search_btn.click()
        time.sleep(3)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        full_text = soup.get_text()
        joined = full_text.replace("\n", " ")

        if "No results found" in joined:
            return (None, full_text)

        # Extract Grantee name
        grantee = None
        lines = full_text.split("\n")
        for i, line in enumerate(lines):
            clean = line.strip()
            if "Grantee" in clean and len(clean) < 30:
                for j in range(i+1, min(i+8, len(lines))):
                    c = lines[j].strip()
                    if c and c not in ("Clear text", "1") and not any(x in c for x in ["Grantor","Recording","Document","Recent","Cart","Filter","Apply","Print","Showing","Sort","(","["]):
                        if len(c) > 2 and len(c) < 120:
                            grantee = c
                        break
                break
        return (grantee, full_text)
    except Exception as e:
        return (None, str(e))

def classify_doc_type(text):
    ut = text.upper()
    if "ASSIGNMENT" in ut and "RENTS" in ut:
        return ("assignment","ASSIGNMENT OF RENTS")
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
        return ("nod","NOTICE OF DEFAULT")
    if any(a in ut for a in ASSIGNMENT_TYPES):
        return ("assignment", next(a for a in ASSIGNMENT_TYPES if a in ut))
    if any(d in ut for d in DEED_TYPES):
        return ("deed", next(d for d in DEED_TYPES if d in ut))
    if " DEED " in ut or ut.endswith("DEED") or ut.startswith("DEED"):
        return ("deed","DEED")
    return ("other", ut[:60])

def parse_owner_name(raw):
    raw = str(raw).strip().upper()
    if not raw or raw in ("NAN","NONE","UNKNOWN","SKIP_TRACE_REQUIRED","COUNTY_REDACTED_NAME"):
        return None
    clean = re.sub(r'\s+(TRUSTEE|TRUST|LIVING TRUST|REVOCABLE TRUST|REVOCABLE|IRA\s*\d*)$', '', raw).strip()
    is_entity = any(m in clean for m in ENTITY_MARKERS)
    if is_entity:
        return {"lastName": clean, "firstName": "", "is_entity": True}
    parts = clean.split()
    if len(parts) == 1:
        return {"lastName": parts[0], "firstName": "", "is_entity": False}
    return {"lastName": parts[0], "firstName": parts[1], "is_entity": False}

def name_search_recorder(page, search_str):
    """Search Tyler by name, return parsed docs."""
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
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(1)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    for li in soup.select("li[class*=ui-li]"):
        text = li.get_text(" ", strip=True)
        doc_match = re.search(r'(\d{4}-\d{7}|\d{10})', text)
        if not doc_match:
            continue
        doc_num = doc_match.group(1)
        cat, sub = classify_doc_type(text)
        docs.append({"doc_number": doc_num, "category": cat, "subtype": sub, "text": text[:200]})
    return docs

def determine_entity_type(name):
    u = name.upper()
    if any(t in u for t in ["TRUST","TRUSTEE"]): return "trust"
    if any(t in u for t in ["LLC","LIMITED LIABILITY"]): return "LLC"
    if any(t in u for t in ["INC","CORP","CORPORATION","PC"]): return "corporate"
    if any(t in u for t in ["LP","LIMITED PARTNERSHIP"]): return "partnership"
    if any(t in u for t in ["CITY","COUNTY","STATE","FEDERAL","UNITED STATES"]): return "government"
    if any(t in u for t in ["BANK","MORTGAGE","LENDING","CREDIT","FINANCIAL"]): return "lender"
    return "individual"

def score_lead(liens=0, has_mortgage=False, has_assignment_rents=False,
               has_affidavit_death=False, tax_delinquent=False, tax_balance=0.0, out_of_state=False,
               has_trustee_deed=False, has_nod=False):
    score = 0
    reasons = []
    if has_assignment_rents:
        score += 28; reasons.append("Assignment of Rents")
    if tax_delinquent:
        score += 25; reasons.append("Tax Delinquency")
        if tax_balance > 1000:
            bonus = min(10, int(tax_balance / 200))
            score += bonus; reasons.append("High Tax Balance")
    if has_mortgage:
        score += 20; reasons.append("Mortgage Recorded")
    if liens > 0:
        score += min(15, liens * 5); reasons.append("%d Active Liens" % liens)
    if has_affidavit_death:
        score += 8; reasons.append("Affidavit of Death")
    if out_of_state:
        score += 5; reasons.append("Out of State Owner")
    if has_nod:
        score += 5; reasons.append("Notice of Default")
    if has_trustee_deed:
        score += 10; reasons.append("Trustee's Deed (post-foreclosure)")
    return min(100, score), "; ".join(reasons)

def run():
    print("=" * 60)
    print("BUTTE AUCTION ENRICHMENT v2 — Aug 7, 2026 Reoffer")
    print("=" * 60)

    # Load authoritative index
    idx = {}
    with open(IDX_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            idx[row["apn_dash"].strip()] = row

    # Build parcel list
    parcels = []
    for apn_dash in AUCTION_APNS:
        info = idx.get(apn_dash, {})
        asmt = info.get("asmt","").strip()
        address = info.get("address","").strip()
        parcels.append({"apn_dash": apn_dash, "asmt": asmt, "address": address})

    print("\n[Step 1] Target parcels: %d" % len(parcels))

    # Step 2: AsrPrint for doc_numbers
    print("\n[Step 2] Fetching doc_numbers from AsrPrint...")
    padded = [p["asmt"] for p in parcels if p["asmt"]]
    asr = batch_asrprint(padded)
    for p in parcels:
        r = asr.get(p["asmt"], {})
        p["doc_number"] = r.get("doc_number")

    valid_docs = [p for p in parcels if p.get("doc_number")]
    print("  Doc numbers found: %d / %d" % (len(valid_docs), len(parcels)))

    # Step 3: Search recorder by doc_number -> Grantee name
    print("\n[Step 3] Resolving owner names via recorder doc search...")
    print("  (~15s per doc = ~%d min)" % int(len(valid_docs) * 15 / 60))

    grantee_map = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)
        disc = page.locator("#submitDisclaimerAccept")
        if disc.count() > 0:
            for _ in range(30):
                try:
                    disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                    if not disabled:
                        disc.click(); time.sleep(3); break
                except:
                    pass
                time.sleep(0.5)

        for idx, parcel in enumerate(valid_docs):
            apn = parcel["apn_dash"]
            doc = parcel["doc_number"]
            rec_fmt = recorder_format(doc)
            if not rec_fmt:
                grantee_map[apn] = None
                continue
            grantee, _ = grantee_from_recorder(page, rec_fmt)
            grantee_map[apn] = grantee
            g = grantee or "NO_NAME"
            if (idx + 1) % 5 == 0 or True:
                print("  [%d/%d] %s doc=%s -> %s" % (idx+1, len(valid_docs), apn, rec_fmt, g[:40] if g else "NONE"))

        browser.close()

    for p in parcels:
        p["grantee"] = grantee_map.get(p["apn_dash"])

    resolved = sum(1 for p in parcels if p.get("grantee"))
    print("  Owner names resolved: %d / %d" % (resolved, len(parcels)))

    # Step 4: Name search for liens/mortgages
    name_searchable = [p for p in parcels if p.get("grantee") and parse_owner_name(p["grantee"])]
    print("\n[Step 4] Searching recorder by owner name for liens/mortgages...")
    print("  (~15s per name = ~%d min for %d names)" % (int(len(name_searchable)*15/60), len(name_searchable)))

    name_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)
        try:
            disc = page.locator("#submitDisclaimerAccept")
            if disc.count() > 0:
                disc.click(timeout=5000); time.sleep(2); page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass
        time.sleep(2)

        for idx, parcel in enumerate(name_searchable):
            apn = parcel["apn_dash"]
            parsed = parse_owner_name(parcel["grantee"])
            search_str = "%s %s" % (parsed["lastName"], parsed["firstName"])
            try:
                docs = name_search_recorder(page, search_str.strip())
                name_results[apn] = docs
            except Exception as e:
                name_results[apn] = []
                try:
                    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=15000); time.sleep(2)
                except:
                    pass

            if (idx + 1) % 5 == 0:
                dcount = len(name_results.get(apn, []))
                print("  [%d/%d] %s %-30s docs=%d" % (idx+1, len(name_searchable), apn, search_str[:30], dcount))

        browser.close()

    # Step 5: Score
    print("\n[Step 5] Scoring...")

    min_bids = {}
    import pdfplumber
    with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.split('\n'):
                    m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+)\s+\$?\s*([\d,]+)\s*$', line.strip())
                    if m:
                        min_bids[m.group(1)] = m.group(3)

    fieldnames = ["apn_dash","asmt","address","owner_name","min_bid",
        "entity_type","total_open_mortgages","open_lien_types",
        "has_assignment_of_rents","notice_of_default_present","has_trustee_deed",
        "recorder_doc_count","recorder_chain","score","score_reasons"]

    output = []
    for parcel in parcels:
        apn = parcel["apn_dash"]
        docs = name_results.get(apn, [])

        lien_types = set()
        mortgage_count = 0
        has_assignment = False
        has_nod = False
        has_reconveyance = False
        has_trustee_deed = False
        chain_parts = []

        for d in docs:
            cat = d["category"]
            if cat == "lien": lien_types.add(d["subtype"])
            elif cat == "mortgage": mortgage_count += 1
            elif cat == "assignment": has_assignment = True
            elif cat == "nod": has_nod = True
            elif cat == "reconveyance": has_reconveyance = True
            elif cat == "trustee_deed": has_trustee_deed = True
            key = d["doc_number"] + "|" + d["subtype"]
            if not any(key in c for c in chain_parts):
                chain_parts.append("%s %s" % (d["doc_number"], d["subtype"]))

        net_mortgages = max(0, mortgage_count - (1 if has_reconveyance else 0))
        entity_type = determine_entity_type(parcel.get("grantee","")) if parcel.get("grantee") else ""

        s, reasons = score_lead(
            liens=len(lien_types),
            has_mortgage=net_mortgages > 0,
            has_assignment_rents=has_assignment,
            has_trustee_deed=has_trustee_deed,
            has_nod=has_nod,
            tax_delinquent=True,
        )

        output.append({
            "apn_dash": apn,
            "asmt": parcel["asmt"],
            "address": parcel["address"],
            "owner_name": parcel.get("grantee",""),
            "min_bid": min_bids.get(apn,""),
            "entity_type": entity_type,
            "total_open_mortgages": str(net_mortgages),
            "open_lien_types": "; ".join(sorted(lien_types)),
            "has_assignment_of_rents": "True" if has_assignment else "False",
            "notice_of_default_present": "True" if has_nod else "False",
            "has_trustee_deed": "True" if has_trustee_deed else "False",
            "recorder_doc_count": str(len(docs)),
            "recorder_chain": " | ".join(chain_parts),
            "score": str(s),
            "score_reasons": reasons,
        })

    output.sort(key=lambda r: int(r["score"]) if r["score"].isdigit() else 0, reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(output)

    print("\nWrote %d rows to %s" % (len(output), OUTPUT_CSV))
    scored50 = [r for r in output if r["score"] and int(r["score"]) >= 50]
    scored70 = [r for r in output if r["score"] and int(r["score"]) >= 70]

    print("\n=== SUMMARY ===")
    print("Total enriched: %d" % len(output))
    print("  Score >= 50: %d" % len(scored50))
    print("  Score >= 70: %d" % len(scored70))
    print("  Owner names resolved: %d" % resolved)
    print("  With mortgages: %d" % len([r for r in output if r["total_open_mortgages"] and int(r["total_open_mortgages"]) > 0]))
    print("  With liens: %d" % len([r for r in output if r["open_lien_types"]]))

    print("\n=== TOP RESULTS ===")
    for r in output[:15]:
        bid = "$%s" % r["min_bid"] if r["min_bid"] else "?"
        print("%-18s | %-30s | %s | %s | %s| %s" % (
            r["apn_dash"], (r["owner_name"] or "")[:30], r["score"].rjust(5),
            r["total_open_mortgages"].rjust(3), bid.rjust(9), r["open_lien_types"][:35]))

    # Also write to existing scored rerun format for compatibility
    print("\nDone. Next: merge with the 14 already-enriched parcels for full targeting list.")
    print("  python merge_auction_targets.py")

if __name__ == "__main__":
    run()
