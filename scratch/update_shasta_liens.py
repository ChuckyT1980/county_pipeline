"""Update shasta_MASTER_leads_with_liens.csv with actual lien results"""
import json, csv, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load lien results
results = json.load(open(os.path.join(base_dir, "scratch/shasta_lien_results.json")))

# Build apn -> lien data lookup
apn_to_lien = {}
for r in results:
    owner = r.get("owner", {})
    apn = owner.get("apn", "")
    if apn:
        apn_to_lien[apn] = {
            "active_liens": r.get("active_liens", 0),
            "mortgages": r.get("mortgages_net", r.get("mortgages", 0)),
            "has_assignment_of_rents": r.get("has_assignment_of_rents", False),
            "has_affidavit_of_death": r.get("has_affidavit_of_death", False),
            "ownership_status": r.get("ownership_status", "Current"),
        }
    # Also store by owner name
    name = owner.get("name", "")
    print(f"  lien data: name='{name}' apn='{apn}' liens={r.get('active_liens',0)}")

# Read and update enriched file
enriched_path = os.path.join(base_dir, "tax_pipeline/shasta_MASTER_leads_with_liens.csv")
rows = []
with open(enriched_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        fee = row.get("fee_parcel", "").strip()
        if fee in apn_to_lien:
            l = apn_to_lien[fee]
            row["active_liens"] = l["active_liens"]
            row["mortgages"] = l["mortgages"]
            row["has_assignment_of_rents"] = l["has_assignment_of_rents"]
            row["has_affidavit_of_death"] = l["has_affidavit_of_death"]
            row["ownership_status"] = l["ownership_status"]
        rows.append(row)

with open(enriched_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nUpdated {len(rows)} rows in {enriched_path}")
updated = sum(1 for r in rows if r.get("fee_parcel", "").strip() in apn_to_lien)
print(f"Updated lien data for {updated} parcels")

# Show updated rows
print(f"\nUpdated parcels:")
for r in rows:
    fee = r.get("fee_parcel", "").strip()
    if fee in apn_to_lien:
        print(f"  {fee:20s} liens={r['active_liens']:3}  mortgages={r['mortgages']:2}  owner={r.get('owner_name','')[:30]}")
