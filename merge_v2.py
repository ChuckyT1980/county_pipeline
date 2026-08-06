import csv
from pathlib import Path

def norm_apn(raw):
    if not raw:
        return ""
    return str(raw).strip().replace("-", "").replace(".0", "").replace(",", "")

def get_apn(row):
    for key in ("fee_parcel", "apn", "APN", "apn_pdf", "asmt"):
        v = row.get(key, "")
        if v and str(v).strip():
            return norm_apn(v)
    return ""

def merge_val(*vals):
    for v in vals:
        if v is not None and str(v).strip() not in ("", "N/A", "None", "null"):
            return str(v).strip()
    return ""

BASE = Path(__file__).parent

shasta = list(csv.DictReader(open(BASE / "tax_pipeline" / "shasta_MASTER_leads_with_liens.csv", newline='', encoding='utf-8-sig')))
tehama = list(csv.DictReader(open(BASE / "tax_pipeline" / "tehama_MASTER_leads_with_liens.csv", newline='', encoding='utf-8-sig')))
crm = list(csv.DictReader(open(BASE / "crm_ready_leads.csv", newline='', encoding='utf-8-sig')))
te_export = list(csv.DictReader(open(BASE / "tehama_all_leads_export.csv", newline='', encoding='utf-8-sig')))
shasta_assessed = list(csv.DictReader(open(BASE / "shasta_assessed_values.csv", newline='', encoding='utf-8-sig')))

crm_lookup = {}
for r in crm:
    crm_lookup[get_apn(r)] = r

te_lookup = {}
for r in te_export:
    te_lookup[get_apn(r)] = r

sa_lookup = {}
for r in shasta_assessed:
    sa_lookup[get_apn(r)] = r

print(f"Sources: Shasta={len(shasta)} Tehama={len(tehama)} CRM={len(crm)} TehExport={len(te_export)} ShastaAssessed={len(shasta_assessed)}")

FIELDS = [
    "county", "score", "confidence",
    "apn", "fee_parcel", "address", "situs_address",
    "owner_name", "assessee_name", "mailing_address", "best_phone",
    "total_balance", "live_total_balance", "delinquent",
    "inst1_status", "inst2_status", "live_paid_status",
    "active_liens", "mortgages",
    "has_assignment_of_rents", "has_affidavit_of_death", "ownership_status",
    "net_assessed_value", "land_value", "improvement_value",
    "acres", "property_type", "lot_acres", "legal_desc",
    "rec_doc_number", "rec_doc_date", "most_recent_deed_date",
    "asmt_status",
    "motivation_reason_text", "Export_Tier", "Verification Status",
    "verified_url", "verified_at",
    "default_year", "years_unpaid", "roll_cat", "source",
]

master = []
apns_seen = set()

for row in shasta:
    apn_key = get_apn(row)
    if not apn_key or apn_key in apns_seen:
        continue
    apns_seen.add(apn_key)

    c = crm_lookup.get(apn_key, {})
    te = te_lookup.get(apn_key, {})
    sa = sa_lookup.get(apn_key, {})

    entry = {
        "county": "shasta",
        "score": merge_val(row.get("verified_score"), row.get("score")),
        "confidence": merge_val(row.get("confidence")),
        "apn": merge_val(row.get("APN"), row.get("fee_parcel")),
        "fee_parcel": merge_val(row.get("fee_parcel"), row.get("APN")),
        "address": merge_val(row.get("address"), row.get("situs_pdf"), sa.get("situs_address")),
        "situs_address": merge_val(row.get("situs_pdf"), sa.get("situs_address")),
        "owner_name": merge_val(row.get("owner_name"), row.get("assessee_name"), c.get("assessee_name"), te.get("assessee_name")),
        "assessee_name": merge_val(row.get("assessee_name"), c.get("assessee_name"), te.get("assessee_name")),
        "mailing_address": merge_val(row.get("mailing_address"), c.get("mailing_address"), te.get("mailing_address")),
        "best_phone": merge_val(c.get("best_phone"), te.get("best_phone")),
        "total_balance": merge_val(row.get("live_total_balance")),
        "live_total_balance": merge_val(row.get("live_total_balance")),
        "delinquent": merge_val(row.get("delinquent"), "True" if row.get("live_paid_status", "") not in ("", "PAID") else "False"),
        "inst1_status": merge_val(row.get("v_inst1_status")),
        "inst2_status": merge_val(row.get("v_inst2_status")),
        "live_paid_status": merge_val(row.get("live_paid_status")),
        "active_liens": merge_val(row.get("active_liens"), c.get("active_liens"), te.get("active_liens")) or "0",
        "mortgages": merge_val(row.get("mortgages"), c.get("mortgages"), te.get("mortgages")) or "0",
        "has_assignment_of_rents": merge_val(str(row.get("has_assignment_of_rents", "")), c.get("has_assignment_of_rents"), te.get("has_assignment_of_rents")),
        "has_affidavit_of_death": merge_val(str(row.get("has_affidavit_of_death", "")), c.get("has_affidavit_of_death"), te.get("has_affidavit_of_death")),
        "ownership_status": merge_val(row.get("ownership_status"), c.get("ownership_status"), te.get("ownership_status")),
        "net_assessed_value": merge_val(sa.get("net_taxable_value"), sa.get("cur_land_value")),
        "land_value": merge_val(sa.get("cur_land_value")),
        "improvement_value": merge_val(sa.get("cur_improvement_value")),
        "acres": merge_val(sa.get("acres")),
        "property_type": merge_val(row.get("property_type")),
        "lot_acres": merge_val(row.get("lot_acres")),
        "legal_desc": merge_val(row.get("legal_desc")),
        "rec_doc_number": merge_val(row.get("rec_doc_number")),
        "rec_doc_date": merge_val(row.get("rec_doc_date")),
        "most_recent_deed_date": merge_val(c.get("most_recent_deed_date")),
        "asmt_status": merge_val(row.get("asmt_status")),
        "motivation_reason_text": merge_val(c.get("motivation_reason_text"), te.get("motivation_reason_text")),
        "Export_Tier": merge_val(c.get("Export_Tier")),
        "Verification Status": merge_val(c.get("Verification Status"), te.get("Verification Status")),
        "verified_url": merge_val(row.get("live_tax_url")),
        "verified_at": merge_val(row.get("live_verified_at")),
        "default_year": merge_val(str(row.get("default_year", "")).replace(".0", "")),
        "years_unpaid": merge_val(str(row.get("years_unpaid", "")).replace(".0", "")),
        "roll_cat": merge_val(row.get("roll_cat"), row.get("roll_cats")),
        "source": "shasta",
    }
    master.append(entry)

for row in tehama:
    apn_key = get_apn(row)
    if not apn_key or apn_key in apns_seen:
        continue
    apns_seen.add(apn_key)

    c = crm_lookup.get(apn_key, {})
    te = te_lookup.get(apn_key, {})

    entry = {
        "county": "tehama",
        "score": merge_val(row.get("verified_score"), row.get("score")),
        "confidence": merge_val(row.get("confidence")),
        "apn": merge_val(row.get("apn_pdf"), row.get("fee_parcel"), row.get("apn")),
        "fee_parcel": merge_val(row.get("fee_parcel"), row.get("apn_pdf")),
        "address": merge_val(row.get("address"), row.get("situs_pdf"), te.get("property_address")),
        "situs_address": merge_val(row.get("situs_pdf")),
        "owner_name": merge_val(row.get("owner_name"), row.get("assessee_name"), c.get("assessee_name"), te.get("assessee_name")),
        "assessee_name": merge_val(row.get("assessee_name"), c.get("assessee_name"), te.get("assessee_name")),
        "mailing_address": merge_val(row.get("mailing_address"), c.get("mailing_address"), te.get("mailing_address")),
        "best_phone": merge_val(c.get("best_phone"), te.get("best_phone")),
        "total_balance": merge_val(row.get("live_total_balance"), row.get("total_stacked_balance")),
        "live_total_balance": merge_val(row.get("live_total_balance")),
        "delinquent": merge_val(row.get("delinquent"), "True" if row.get("live_paid_status", "") not in ("", "PAID") else "False"),
        "inst1_status": merge_val(row.get("v_inst1_status")),
        "inst2_status": merge_val(row.get("v_inst2_status")),
        "live_paid_status": merge_val(row.get("live_paid_status")),
        "active_liens": merge_val(row.get("active_liens"), c.get("active_liens"), te.get("active_liens")) or "0",
        "mortgages": merge_val(row.get("mortgages"), c.get("mortgages"), te.get("mortgages")) or "0",
        "has_assignment_of_rents": merge_val(str(row.get("has_assignment_of_rents", "")), c.get("has_assignment_of_rents"), te.get("has_assignment_of_rents")),
        "has_affidavit_of_death": merge_val(str(row.get("has_affidavit_of_death", "")), c.get("has_affidavit_of_death"), te.get("has_affidavit_of_death")),
        "ownership_status": merge_val(row.get("ownership_status"), c.get("ownership_status"), te.get("ownership_status")),
        "net_assessed_value": merge_val(row.get("net_assessed_value"), te.get("net_assessed_value")),
        "land_value": merge_val(row.get("cur_land_value")),
        "improvement_value": merge_val(row.get("cur_improvement_value")),
        "acres": merge_val(row.get("acres")),
        "property_type": merge_val(row.get("property_type")),
        "lot_acres": merge_val(row.get("lot_acres")),
        "legal_desc": merge_val(row.get("legal_desc")),
        "rec_doc_number": merge_val(row.get("rec_doc_number")),
        "rec_doc_date": merge_val(row.get("rec_doc_date")),
        "most_recent_deed_date": merge_val(c.get("most_recent_deed_date")),
        "asmt_status": merge_val(row.get("asmt_status")),
        "motivation_reason_text": merge_val(c.get("motivation_reason_text"), te.get("motivation_reason_text")),
        "Export_Tier": merge_val(c.get("Export_Tier")),
        "Verification Status": merge_val(c.get("Verification Status"), te.get("Verification Status")),
        "verified_url": merge_val(row.get("live_tax_url")),
        "verified_at": merge_val(row.get("live_verified_at")),
        "default_year": merge_val(str(row.get("default_year", "")).replace(".0", "")),
        "years_unpaid": merge_val(str(row.get("years_unpaid", "")).replace(".0", "")),
        "roll_cat": merge_val(row.get("roll_cats"), row.get("roll_cat")),
        "source": "tehama",
    }
    master.append(entry)

from collections import Counter
counties = Counter(e["county"] for e in master)
print(f"\nTotal: {len(master)} leads ({dict(counties)})")

stats = {
    "Owner": sum(1 for e in master if e["owner_name"]),
    "Mailing": sum(1 for e in master if e["mailing_address"]),
    "Liens (incl 0)": sum(1 for e in master if e["active_liens"] != ""),
    "Assessed value": sum(1 for e in master if e["net_assessed_value"]),
    "Score": sum(1 for e in master if e["score"]),
    "Motivation text": sum(1 for e in master if e["motivation_reason_text"]),
    "Acres": sum(1 for e in master if e["acres"]),
    "Recorder doc": sum(1 for e in master if e["rec_doc_number"]),
}
for k, v in stats.items():
    print(f"  {k}: {v}/{len(master)} ({v*100//len(master)}%)")

outpath = BASE / "northern_ca_MASTER_merged.csv"
with open(outpath, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(master)
print(f"\nWrote: {outpath}")
