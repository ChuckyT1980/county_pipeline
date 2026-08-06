"""Inject real owner names from export into Shasta enriched file"""
import csv, os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Build fee_parcel -> owner_name mapping from export
export_map = {}
with open(os.path.join(base, "northern_ca_MASTER_export_with_owners.csv")) as f:
    for row in csv.DictReader(f):
        if row.get("county", "").strip().lower() == "shasta":
            fee = row.get("fee_parcel", "").strip()
            owner = row.get("owner_name", "").strip()
            if fee and owner and owner != "SKIP_TRACE_REQUIRED":
                export_map[fee] = owner
                export_map[fee.replace("-", "")] = owner

print("Owner map from export:")
for fee, owner in export_map.items():
    print("  %s -> %s" % (fee, owner))

# Update enriched file
enriched_path = os.path.join(base, "tax_pipeline/shasta_MASTER_leads_with_liens.csv")
rows = []
updated = 0
with open(enriched_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        fee = row.get("fee_parcel", "").strip()
        if fee in export_map:
            row["assessee_name"] = export_map[fee]
            row["owner_name"] = export_map[fee]
            updated += 1
        rows.append(row)

with open(enriched_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("\nUpdated %d rows with real owner names" % updated)
