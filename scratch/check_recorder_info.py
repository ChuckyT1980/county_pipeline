"""Check what recorder_info looks like for Shasta rows"""
import csv, os
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(base, 'northern_ca_MASTER_export_with_owners.csv')) as f:
    for r in csv.DictReader(f):
        c = r.get('county','').strip()
        o = r.get('owner_name','').strip()
        rec = r.get('recorder_info','')
        if c == 'shasta' and o:
            print(f"  {o[:35]:35s} rec='{rec}'")
