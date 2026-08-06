"""Check Tehama rows in the export"""
import csv, os
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')) as f:
    for row in csv.DictReader(f):
        c = row.get('county', '').strip()
        r = row.get('recorder_info', '').strip()[:60]
        o = row.get('owner_name', '').strip()[:25]
        bal = row.get('total_balance', '')
        if 'teh' in c.lower():
            print("county='%s' rec='%s' owner='%s' bal=%s" % (c, r, o, bal))
