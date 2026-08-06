"""Trace how Tehama rows without fee_parcel got into the export"""
import csv, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Show all columns for the empty-fee Tehama rows
export_path = os.path.join(base_dir, 'northern_ca_MASTER_export.csv')
with open(export_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    
    # Find Tehama rows without fee_parcel
    empty_rows = []
    for row in reader:
        row = dict(row)
        if row.get('county', '').strip().lower() == 'tehama' and not row.get('fee_parcel', '').strip():
            empty_rows.append(row)
    
    print(f"Tehama rows without fee_parcel: {len(empty_rows)}")
    print(f"Columns: {fieldnames}")
    print()
    for i, row in enumerate(empty_rows):
        print(f"--- Row {i+1} ---")
        for k, v in row.items():
            if v and v.strip():
                print(f"  {k}: {v[:100]}")
        print()

# Also check the MASTER leads file that fed the export
master_path = os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads.csv')
if os.path.exists(master_path):
    print(f"\n\n=== Tehama MASTER leads (first 15 rows) ===")
    with open(master_path) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 15:
                break
            fee = row.get('fee_parcel', row.get('FEEPARCEL', row.get('apn', ''))).strip()
            owner = row.get('owner_name', row.get('OwnerName', row.get('OWNER_NAME', ''))).strip()
            balance = row.get('total_balance', row.get('Balance', row.get('TOTAL_BALANCE', ''))).strip()
            print(f"  fee={fee:20s} owner={owner[:30]:30s} balance={balance:>10s}")
