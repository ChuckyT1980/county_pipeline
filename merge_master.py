import csv, re, json
from pathlib import Path

BASE = Path(__file__).parent

def norm_apn(raw):
    if not raw:
        return ""
    s = str(raw).strip().replace("-", "").replace(".0", "").replace(",", "")
    return s

def get_apn(row):
    """Try multiple APN fields, return normalized"""
    for key in ("fee_parcel", "apn", "APN", "apn_pdf", "asmt"):
        v = row.get(key, "")
        if v and str(v).strip():
            return norm_apn(v)
    return ""

def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def merge_val(*vals):
    for v in vals:
        if v and str(v).strip() and str(v).strip() not in ("", "N/A", "None", "null"):
            return str(v).strip()
    return ""

# Load all sources
shasta = load_csv(BASE / "tax_pipeline" / "shasta_MASTER_leads_with_liens.csv")
tehama = load_csv(BASE / "tax_pipeline" / "tehama_MASTER_leads_with_liens.csv")
crm = load_csv(BASE / "crm_ready_leads.csv")
tehama_export = load_csv(BASE / "tehama_all_leads_export.csv")

print(f"Shasta liens: {len(shasta)}")
print(f"Tehama liens: {len(tehama)}")
print(f"CRM ready: {len(crm)}")
print(f"Tehama export: {len(tehama_export)}")

# Build lookup by normalized APN
crm_lookup = {}
for row in crm:
    apn = norm_apn(row.get("apn", ""))
    crm_lookup[apn] = row

te_export_lookup = {}
for row in tehama_export:
    apn = norm_apn(row.get("apn", ""))
    te_export_lookup[apn] = row

# Fields we want in the final output
FIELDS = [
    "county", "apn", "fee_parcel", "address", "situs_address",
    "total_balance", "total_stacked_balance", "live_total_balance",
    "delinquent", "score", "confidence",
    "inst1_status", "inst2_status", "live_paid_status",
    "owner_name", "assessee_name", "mailing_address", "best_phone",
    "rec_doc_number", "rec_doc_date", "most_recent_deed_date",
    "property_type", "lot_acres", "legal_desc",
    "net_assessed_value", "asmt_status",
    "active_liens", "mortgages",
    "has_assignment_of_rents", "has_affidavit_of_death",
    "ownership_status",
    "motivation_reason_text", "Export_Tier",
    "Verification Status",
    "verified_url", "verified_at",
    "default_year", "years_unpaid", "earliest_year", "latest_year",
    "roll_cat", "source",
]

master = []
apns_seen = set()

# Process Shasta
for row in shasta:
    apn_key = get_apn(row)
    if not apn_key:
        continue
    apns_seen.add(apn_key)

    enrichment = crm_lookup.get(apn_key, {})
    te_export = te_export_lookup.get(apn_key, {})

    entry = {
        "county": merge_val(row.get("county", ""), "shasta"),
        "apn": merge_val(row.get("APN", ""), row.get("fee_parcel", ""), row.get("asmt", "")),
        "fee_parcel": merge_val(row.get("fee_parcel", ""), row.get("APN", "")),
        "address": merge_val(row.get("address", ""), row.get("situs_pdf", ""), row.get("situs_address", "")),
        "situs_address": merge_val(row.get("situs_pdf", ""), row.get("situs_address", "")),
        "total_balance": merge_val(row.get("live_total_balance", ""), row.get("total_balance", "")),
        "total_stacked_balance": "",
        "live_total_balance": merge_val(row.get("live_total_balance", "")),
        "delinquent": merge_val(row.get("delinquent", ""), str(row.get("live_paid_status", "") != "PAID" if row.get("live_paid_status") else "")),
        "score": merge_val(row.get("verified_score", ""), row.get("score", "")),
        "confidence": merge_val(row.get("confidence", "")),
        "inst1_status": merge_val(row.get("inst1_status", "")),
        "inst2_status": merge_val(row.get("inst2_status", "")),
        "live_paid_status": merge_val(row.get("live_paid_status", "")),
        "owner_name": merge_val(row.get("owner_name", ""), row.get("assessee_name", ""), enrichment.get("assessee_name", ""), te_export.get("assessee_name", "")),
        "assessee_name": merge_val(row.get("assessee_name", ""), enrichment.get("assessee_name", ""), te_export.get("assessee_name", "")),
        "mailing_address": merge_val(row.get("mailing_address", ""), enrichment.get("mailing_address", ""), te_export.get("mailing_address", "")),
        "best_phone": merge_val(enrichment.get("best_phone", ""), te_export.get("best_phone", "")),
        "rec_doc_number": merge_val(row.get("rec_doc_number", "")),
        "rec_doc_date": merge_val(row.get("rec_doc_date", "")),
        "most_recent_deed_date": merge_val(enrichment.get("most_recent_deed_date", "")),
        "property_type": merge_val(row.get("property_type", "")),
        "lot_acres": merge_val(row.get("lot_acres", "")),
        "legal_desc": merge_val(row.get("legal_desc", "")),
        "net_assessed_value": merge_val(row.get("net_assessed_value", ""), enrichment.get("net_assessed_value", ""), te_export.get("net_assessed_value", "")),
        "asmt_status": merge_val(row.get("asmt_status", "")),
        "active_liens": merge_val(row.get("active_liens", ""), enrichment.get("active_liens", ""), te_export.get("active_liens", "")),
        "mortgages": merge_val(row.get("mortgages", ""), enrichment.get("mortgages", ""), te_export.get("mortgages", "")),
        "has_assignment_of_rents": merge_val(str(row.get("has_assignment_of_rents", "")), enrichment.get("has_assignment_of_rents", ""), te_export.get("has_assignment_of_rents", "")),
        "has_affidavit_of_death": merge_val(str(row.get("has_affidavit_of_death", "")), enrichment.get("has_affidavit_of_death", ""), te_export.get("has_affidavit_of_death", "")),
        "ownership_status": merge_val(row.get("ownership_status", ""), enrichment.get("ownership_status", ""), te_export.get("ownership_status", "")),
        "motivation_reason_text": merge_val(enrichment.get("motivation_reason_text", ""), te_export.get("motivation_reason_text", "")),
        "Export_Tier": merge_val(enrichment.get("Export_Tier", "")),
        "Verification Status": merge_val(enrichment.get("Verification Status", ""), te_export.get("Verification Status", "")),
        "verified_url": merge_val(row.get("live_tax_url", "")),
        "verified_at": merge_val(row.get("live_verified_at", "")),
        "default_year": merge_val(str(row.get("default_year", "")).replace(".0", "")),
        "years_unpaid": merge_val(str(row.get("years_unpaid", "")).replace(".0", "")),
        "earliest_year": merge_val(str(row.get("earliest_year", "")).replace(".0", "")),
        "latest_year": merge_val(str(row.get("latest_year", "")).replace(".0", "")),
        "roll_cat": merge_val(row.get("roll_cat", ""), row.get("roll_cats", "")),
        "source": merge_val(row.get("source", ""), "shasta"),
    }
    master.append(entry)

# Process Tehama
for row in tehama:
    apn_key = get_apn(row)
    if not apn_key:
        continue
    if apn_key in apns_seen:
        continue
    apns_seen.add(apn_key)

    enrichment = crm_lookup.get(apn_key, {})
    te_export = te_export_lookup.get(apn_key, {})

    entry = {
        "county": merge_val(row.get("county", ""), "tehama"),
        "apn": merge_val(row.get("apn_pdf", ""), row.get("fee_parcel", ""), row.get("apn", "")),
        "fee_parcel": merge_val(row.get("fee_parcel", ""), row.get("apn_pdf", "")),
        "address": merge_val(row.get("address", ""), row.get("situs_pdf", ""), te_export.get("property_address", "")),
        "situs_address": merge_val(row.get("situs_pdf", "")),
        "total_balance": merge_val(row.get("live_total_balance", ""), row.get("total_stacked_balance", "")),
        "total_stacked_balance": merge_val(row.get("total_stacked_balance", "")),
        "live_total_balance": merge_val(row.get("live_total_balance", "")),
        "delinquent": merge_val(str(row.get("live_paid_status", "") != "PAID" if row.get("live_paid_status") else ""), "True"),
        "score": merge_val(row.get("score", "")),
        "confidence": merge_val(row.get("confidence", "")),
        "inst1_status": merge_val(row.get("inst1_status", "")),
        "inst2_status": merge_val(row.get("inst2_status", "")),
        "live_paid_status": merge_val(row.get("live_paid_status", "")),
        "owner_name": merge_val(row.get("owner_name", ""), row.get("assessee_name", ""), enrichment.get("assessee_name", ""), te_export.get("assessee_name", "")),
        "assessee_name": merge_val(row.get("assessee_name", ""), enrichment.get("assessee_name", ""), te_export.get("assessee_name", "")),
        "mailing_address": merge_val(row.get("mailing_address", ""), enrichment.get("mailing_address", ""), te_export.get("mailing_address", "")),
        "best_phone": merge_val(enrichment.get("best_phone", ""), te_export.get("best_phone", "")),
        "rec_doc_number": merge_val(row.get("rec_doc_number", "")),
        "rec_doc_date": merge_val(row.get("rec_doc_date", "")),
        "most_recent_deed_date": merge_val(enrichment.get("most_recent_deed_date", "")),
        "property_type": merge_val(row.get("property_type", "")),
        "lot_acres": merge_val(row.get("lot_acres", "")),
        "legal_desc": merge_val(row.get("legal_desc", "")),
        "net_assessed_value": merge_val(row.get("net_assessed_value", ""), te_export.get("net_assessed_value", "")),
        "asmt_status": merge_val(row.get("asmt_status", "")),
        "active_liens": merge_val(row.get("active_liens", ""), enrichment.get("active_liens", ""), te_export.get("active_liens", "")),
        "mortgages": merge_val(row.get("mortgages", ""), enrichment.get("mortgages", ""), te_export.get("mortgages", "")),
        "has_assignment_of_rents": merge_val(str(row.get("has_assignment_of_rents", "")), enrichment.get("has_assignment_of_rents", ""), te_export.get("has_assignment_of_rents", "")),
        "has_affidavit_of_death": merge_val(str(row.get("has_affidavit_of_death", "")), enrichment.get("has_affidavit_of_death", ""), te_export.get("has_affidavit_of_death", "")),
        "ownership_status": merge_val(row.get("ownership_status", ""), enrichment.get("ownership_status", ""), te_export.get("ownership_status", "")),
        "motivation_reason_text": merge_val(enrichment.get("motivation_reason_text", ""), te_export.get("motivation_reason_text", "")),
        "Export_Tier": merge_val(enrichment.get("Export_Tier", "")),
        "Verification Status": merge_val(enrichment.get("Verification Status", ""), te_export.get("Verification Status", "")),
        "verified_url": merge_val(row.get("live_tax_url", "")),
        "verified_at": merge_val(row.get("live_verified_at", "")),
        "default_year": merge_val(str(row.get("default_year", "")).replace(".0", "")),
        "years_unpaid": merge_val(str(row.get("years_unpaid", "")).replace(".0", "")),
        "earliest_year": merge_val(str(row.get("earliest_year", "")).replace(".0", "")),
        "latest_year": merge_val(str(row.get("latest_year", "")).replace(".0", "")),
        "roll_cat": merge_val(row.get("roll_cats", ""), row.get("roll_cat", "")),
        "source": merge_val(row.get("source", ""), "tehama"),
    }
    master.append(entry)

print(f"\nMaster merge: {len(master)} total leads ({len(apns_seen)} unique APNs)")

# Stats
from collections import Counter
county_counts = Counter(e["county"] for e in master)
print(f"By county: {dict(county_counts)}")

scored = sum(1 for e in master if e["score"])
has_owner = sum(1 for e in master if e["owner_name"])
has_mail = sum(1 for e in master if e["mailing_address"])
has_liens = sum(1 for e in master if e["active_liens"])
has_assessed = sum(1 for e in master if e["net_assessed_value"])
has_motivation = sum(1 for e in master if e["motivation_reason_text"])

print(f"Has score: {scored}")
print(f"Has owner: {has_owner}")
print(f"Has mailing: {has_mail}")
print(f"Has liens: {has_liens}")
print(f"Has assessed value: {has_assessed}")
print(f"Has motivation text: {has_motivation}")

outpath = BASE / "northern_ca_MASTER_merged.csv"
with open(outpath, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(master)

print(f"\nWrote: {outpath}")
print("Done.")
