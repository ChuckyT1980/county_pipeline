import os, glob, pandas as pd

key_files = [
    ('leads_for_sale.csv', 'Final sellable leads'),
    ('sample_5_clean_leads.csv', 'Buyer sample'),
    ('all_seller_intent_HIGH.csv', 'HIGH intent leads'),
    ('all_seller_intent_HIGH_sellable.csv', 'Transfer-clean leads'),
    ('transfer_review_queue.csv', 'Transfer review queue'),
    ('batch_checkpoint.json', 'Batch progress'),
    ('all_counties_enriched_leads.csv', 'Combined county data'),
    ('tax_pipeline/shasta_MASTER_leads_with_liens.csv', 'Shasta MASTER'),
    ('tax_pipeline/tehama_MASTER_leads_with_liens.csv', 'Tehama MASTER'),
    ('tax_pipeline/lassen_MASTER_leads_with_liens.csv', 'Lassen MASTER'),
    ('tax_pipeline/butte_MASTER_leads_with_liens.csv',  'Butte MASTER'),
]

print("KEY FILES:")
for path, label in key_files:
    if os.path.exists(path):
        size = os.path.getsize(path)
        if path.endswith('.csv'):
            try:
                df = pd.read_csv(path)
                print("  OK    %-30s %3d rows  (%.1f KB)" % (label, len(df), size/1024))
            except Exception:
                print("  OK    %-30s %.1f KB (read error)" % (label, size/1024))
        else:
            print("  OK    %-30s %d bytes" % (label, size))
    else:
        print("  MISS  %-30s" % label)

print()
print("CLUTTER:")
print("  Debug HTML in root  : %d" % len(glob.glob("*.html")))
print("  Debug PNG in root   : %d" % len(glob.glob("*.png")))
print("  Stale test CSVs root: %d" % len(glob.glob("*_test_book*.csv")))
cfv = len(glob.glob("cfv*.py")) + len(glob.glob("mar1*.py")) + len(glob.glob("lril*.py"))
print("  Theory framework py : %d" % cfv)
total = len([f for f in os.listdir('.') if os.path.isfile(f)])
print("  Total root files    : %d" % total)

print()
print("LARGE FILES (>500 KB):")
big = []
for pattern in ("*.csv", "*.json", "*.parquet", "tax_pipeline/*.csv", "tax_pipeline/*.parquet"):
    for f in glob.glob(pattern):
        s = os.path.getsize(f)
        if s > 500000:
            big.append((f, s))
big.sort(key=lambda x: x[1], reverse=True)
for f, s in big[:10]:
    print("  %.1f MB  %s" % (s/1024/1024, f))
