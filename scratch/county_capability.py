import csv

with open('scratch/all_county_platforms.csv', encoding='utf-8') as f:
    counties = list(csv.DictReader(f))

mpts_live   = [c for c in counties if c['assessor_backend'] == 'mpts']
arcgis_live = [c for c in counties if c['assessor_backend'] == 'arcgis']
csv_local   = [c for c in counties if c['assessor_backend'] == 'csv']
manual_only = [c for c in counties if c['assessor_backend'] == 'manual']
tyler_rec   = [c for c in counties if c['recorder_backend'] == 'tyler']

print("=== ASSESSOR EXTRACTION ===")
print(f"MPTS live pull (adapter proven): {len(mpts_live)} counties")
for c in mpts_live:
    print(f"  - {c['county']}")

print()
print(f"ArcGIS FeatureServer (proven): {len(arcgis_live)} counties")
for c in arcgis_live:
    print(f"  - {c['county']}")

print()
print(f"CSV local only (no live pull yet): {len(csv_local)} counties")
for c in csv_local:
    print(f"  - {c['county']}")

print()
print(f"manual backend (no adapter built): {len(manual_only)} counties")
for c in manual_only:
    print(f"  - {c['county']}")

print()
print("=== RECORDER EXTRACTION ===")
print(f"Tyler EagleWeb (adapter proven): {len(tyler_rec)} counties")
for c in tyler_rec:
    print(f"  - {c['county']}")
