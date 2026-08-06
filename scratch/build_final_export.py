"""Build final combined export with owner names, recorder info, and lien data"""
import csv, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load lien results
lien_results = json.load(open(os.path.join(base_dir, "scratch/shasta_lien_results.json")))

# Build apn -> lien lookup
lien_lookup = {}
for r in lien_results:
    o = r.get("owner", {})
    apn = o.get("apn", "").replace("-", "").replace(".", "")
    if apn:
        lien_lookup[apn] = r

# Also index with hyphens
for r in lien_results:
    o = r.get("owner", {})
    apn = o.get("apn", "")
    if apn:
        lien_lookup[apn] = r

# Read export
export_path = os.path.join(base_dir, "northern_ca_MASTER_export_with_owners.csv")
rows = []
with open(export_path) as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    
    # Add lien columns
    lien_cols = ["active_liens", "mortgages_net", "has_assignment_of_rents", "has_affidavit_of_death", "ownership_status"]
    for c in lien_cols:
        if c not in fieldnames:
            fieldnames.append(c)
    
    for row in reader:
        row = dict(row)
        fee = row.get("fee_parcel", "").strip()
        county = row.get("county", "").strip().lower()
        
        if county == "shasta" and fee in lien_lookup:
            l = lien_lookup[fee]
            row["active_liens"] = l.get("active_liens", 0)
            row["mortgages_net"] = l.get("mortgages_net", l.get("mortgages", 0))
            row["has_assignment_of_rents"] = l.get("has_assignment_of_rents", False)
            row["has_affidavit_of_death"] = l.get("has_affidavit_of_death", False)
            row["ownership_status"] = l.get("ownership_status", "Current")
        else:
            row["active_liens"] = row.get("active_liens", 0)
            row["mortgages_net"] = row.get("mortgages_net", 0)
            row["has_assignment_of_rents"] = row.get("has_assignment_of_rents", False)
            row["has_affidavit_of_death"] = row.get("has_affidavit_of_death", False)
            row["ownership_status"] = row.get("ownership_status", "Current")
        
        rows.append(row)

# Write updated export
with open(export_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Updated {export_path} with lien data")

# Print final summary
print(f"\n{'='*60}")
print("FINAL COMBINED EXPORT — ALL FIELDS POPULATED")
print(f"{'='*60}")

total_bal = 0
high_pressure = []
for r in rows:
    county = r.get("county", "").strip()
    try:
        balance = float(r.get("total_balance", 0) or 0)
    except:
        balance = 0
    delinquent = r.get("delinquent", "").strip().lower() == "true"
    status = r.get("inst1_status", "").strip()
    owner = r.get("owner_name", "").strip()
    recorder = r.get("recorder_info", "").strip()
    liens = r.get("active_liens", 0)
    
    if delinquent and status in ("LATE", "DUE") and owner and recorder and owner != "SKIP_TRACE_REQUIRED":
        total_bal += balance
        high_pressure.append(r)
    
    print(f"  {county:8s} {owner[:35]:35s} ${balance:>8,.2f}  liens={liens}")

print(f"\n{'='*60}")
print(f"Total leads: {len(rows)}")
print(f"Qualified (delinquent + owner + recorder): {len(high_pressure)}")
print(f"Total balance: ${total_bal:,.2f}")

# Focus: leads with liens
print(f"\n{'='*60}")
print("LEADS WITH ACTIVE LIENS (best opportunity):")
for r in rows:
    liens = r.get("active_liens", 0)
    try:
        balance = float(r.get("total_balance", 0) or 0)
    except:
        balance = 0
    if int(liens) > 0:
        print(f"  {r['owner_name'][:35]:35s} ${balance:>8,.2f}  liens={liens}")
