"""
outreach_generator.py — Bulk Claim Letter & Agreement Generator
=============================================================
Generates personalized, ready-to-print claim packages and contingency 
agreements for former property owners with unclaimed excess proceeds.

Usage:
  python outreach_generator.py --county humboldt
  python outreach_generator.py --county butte
"""

import argparse
import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SURPLUS_DB = ROOT / "surplus.sqlite"
OUT_DIR = ROOT / "output" / "outreach"

LETTER_TEMPLATE = """# NOTICE OF UNCLAIMED PROPERTY SURPLUS FUNDS

**DATE:** {today}  
**PARCEL ID (APN):** {apn}  
**COUNTY:** {county_name} County, California  
**CLAIM DEADLINE:** {deadline}  

---

### IMPORTANT LEGAL NOTICE REGARDING YOUR FORMER PROPERTY

Dear **{owner_name}**,

Our public records search indicates that **{county_name} County** is currently holding unclaimed surplus funds resulting from the tax-deed sale of property formerly registered under your name.

* **Estimated Surplus Funds Available:** **${excess_amount:,.2f}**
* **Statutory Claim Deadline:** **{deadline}** *(Under CA Revenue & Taxation Code § 4675)*

---

### YOUR RIGHTS AND RECOVERY OPTIONS

Under California law, former owners of record retain the legal right to claim these excess proceeds before the statutory deadline. If uncollected before the deadline, these funds **escheat permanently to the county general fund**.

### OUR CONTINGENCY RECOVERY SERVICE

We specialize in processing and recovering excess proceeds claims across California.

* **Zero Upfront Cost:** You pay nothing out of pocket.
* **100% Contingency-Based:** Our recovery fee (35%) is collected ONLY if and when the county approves and issues your check.
* **Complete Claim Filing:** We prepare all notarized affidavits, deed verification documentation, and board of supervisors claim forms on your behalf.

---

### NEXT STEPS TO CLAIM YOUR FUNDS

1. Review and sign the attached **Contingency Recovery Authorization**.
2. Return the signed form via the pre-paid envelope or scan and email to `claims@norcalpropintel.com`.
3. Our legal processing team will submit your claim directly to the {county_name} County Auditor-Controller.

Sincerely,  

**NorCal Property Intelligence & Claims Recovery Team**  
*California Tax Deed Overage Division*  
Phone: (800) 555-0199  
Email: claims@norcalpropintel.com  
"""

def generate_outreach(county: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    county_out = OUT_DIR / county
    county_out.mkdir(parents=True, exist_ok=True)
    
    # Try surplus DB first, fallback to CSV
    records = []
    if SURPLUS_DB.exists():
        conn = sqlite3.connect(SURPLUS_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM surplus_opportunities WHERE LOWER(county) = ?", (county.lower(),))
        records = [dict(r) for r in cur.fetchall()]
        conn.close()
        
    if not records:
        csv_candidates = [
            ROOT / "data" / "counties" / county / "excess_proceeds.csv",
            ROOT / "excess_proceeds" / f"excess_proceeds_{county}_2026.csv",
            ROOT / "excess_proceeds" / f"excess_proceeds_{county}_2025.csv",
            ROOT / "tax_pipeline" / f"{county}_auction_all_105_enriched.csv",
            ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
        ]
        for p in csv_candidates:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        apn = row.get("apn") or row.get("apn_dash") or row.get("APN", "")
                        owner = row.get("owner") or row.get("owner_name") or row.get("former_owner") or row.get("Owner of Record", "Property Owner")
                        amt_str = row.get("excess_proceeds") or row.get("surplus") or row.get("excess_amount") or "0"
                        try:
                            amt = float(str(amt_str).replace("$","").replace(",","").strip() or 0)
                        except:
                            amt = 0.0
                        deadline = row.get("claim_deadline") or row.get("deadline") or "2027-06-18"
                        records.append({
                            "apn": apn,
                            "county": county,
                            "owner": owner,
                            "excess_amount": amt,
                            "claim_deadline": deadline
                        })
                break
                
    if not records:
        print(f"[outreach_generator] No claim records found for '{county}'.")
        return False
        
    generated = 0
    today_str = datetime.now().strftime("%B %d, %Y")
    county_name = county.replace("_", " ").title()
    
    conn = sqlite3.connect(SURPLUS_DB)
    now_iso = datetime.now().isoformat()
    
    for r in records:
        apn = r.get("apn", "")
        if not apn:
            continue
            
        owner = r.get("owner") or "Property Owner"
        amount = r.get("excess_amount") or 0.0
        deadline = r.get("claim_deadline") or "2027-06-18"
        
        letter_content = LETTER_TEMPLATE.format(
            today=today_str,
            apn=apn,
            county_name=county_name,
            owner_name=owner,
            excess_amount=amount,
            deadline=deadline
        )
        
        safe_apn = apn.replace("-", "").strip()
        out_filename = county_out / f"{county}_{safe_apn}_outreach_letter.md"
        with open(out_filename, "w", encoding="utf-8") as f:
            f.write(letter_content)
            
        # Update DB status
        try:
            conn.execute("""
                UPDATE surplus_opportunities 
                SET letter_sent_date = ? 
                WHERE apn = ?
            """, (now_iso, apn))
        except:
            pass
            
        generated += 1
        
    conn.commit()
    conn.close()
    
    print(f"[outreach_generator] Successfully generated {generated} outreach packages for '{county}'.")
    print(f"[outreach_generator] Saved letters to: {county_out}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outreach Letter & Claim Package Generator")
    parser.add_argument("--county", required=True, help="County slug (e.g. humboldt, butte, tehama)")
    args = parser.parse_args()
    
    generate_outreach(args.county.lower())
