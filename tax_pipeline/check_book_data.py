import csv, os

arch = r"C:\Users\chuck\Downloads\county_pipeline\archive"
files = [f for f in os.listdir(arch) if f.startswith("butte_test_book")]

for f in sorted(files):
    with open(os.path.join(arch, f)) as fh:
        rows = list(csv.DictReader(fh))
    k = list(rows[0].keys())
    oc = [c for c in k if any(x in c.lower() for x in ["owner", "name", "assessee"])]
    has_owner = sum(1 for r in rows if r.get("assessee_name","").strip()) if "assessee_name" in k else 0
    sample_apn = rows[0].get("asmt","") if "asmt" in k else rows[0].get("fee_parcel","")
    sample_name = rows[0].get("assessee_name","MISSING_COLUMN") if "assessee_name" in k else "MISSING_COLUMN"
    print(f"{f}: {len(rows)} rows, {len(k)} cols")
    print(f"  Owner cols: {oc}")
    print(f"  Has names: {has_owner}/{len(rows)}")
    print(f"  Sample: apn={sample_apn}, assessee_name={sample_name[:60] if sample_name else 'EMPTY'}")
    print()
