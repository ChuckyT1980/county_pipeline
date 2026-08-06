import csv, os

arch = r"C:\Users\chuck\Downloads\county_pipeline\archive"
files = [f for f in os.listdir(arch) if f.startswith("butte_crm") and f.endswith(".csv")]
print("Enriched output files:")
for f in sorted(files):
    with open(os.path.join(arch, f)) as fh:
        r = list(csv.DictReader(fh))
    print(f"  {f}: {len(r)} rows")
    if r:
        k = list(r[0].keys())
        print(f"    Cols: {k}")
        # Check owner fields
        owner_cols = [c for c in k if any(x in c.lower() for x in ["owner", "name", "assessee"])]
        print(f"    Owner cols: {owner_cols}")
        # How many have owner_name populated?
        if "owner_name" in k:
            missing = sum(1 for row in r if not row.get("owner_name","").strip() or row.get("owner_name") == "COUNTY_REDACTED_NAME" or row.get("owner_name") == "SKIP_TRACE_REQUIRED")
            print(f"    Missing owner_name: {missing}/{len(r)}")
        if "assessee_name" in k:
            missing = sum(1 for row in r if not row.get("assessee_name","").strip())
            print(f"    Missing assessee_name: {missing}/{len(r)}")
        # Show a sample row
        print(f"    Sample:")
        for row in r[:1]:
            for c in ["apn", "owner_name", "assessee_name", "asrprint_status", "taxbill_status", "owner_source"]:
                val = row.get(c, "")
                print(f"      {c} = {val}")
        print()
