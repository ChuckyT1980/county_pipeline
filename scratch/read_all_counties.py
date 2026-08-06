import yaml, os, glob, csv

yaml_dir = 'counties'
results = []
for yf in sorted(glob.glob(f'{yaml_dir}/*.yaml')):
    county = os.path.splitext(os.path.basename(yf))[0]
    with open(yf, encoding='utf-8') as f:
        d = yaml.safe_load(f)
    assessor = d.get('assessor', {}) or {}
    recorder = d.get('recorder', {}) or {}
    auction  = d.get('auction', {}) or {}
    ab = assessor.get('backend', '-')
    ae = assessor.get('endpoint', '') or assessor.get('host', '')
    rb = recorder.get('backend', '-')
    ru = recorder.get('base_url', '')
    rni = recorder.get('name_search_id', '')
    aub = auction.get('backend', '-')
    print(f"{county:22s}  assessor={ab:12s}  recorder={rb:10s}  auction={aub}")
    results.append({'county': county, 'assessor_backend': ab, 'assessor_endpoint': ae,
                    'recorder_backend': rb, 'recorder_url': ru, 'recorder_name_id': rni,
                    'auction_backend': aub})

with open('scratch/all_county_platforms.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['county','assessor_backend','assessor_endpoint','recorder_backend','recorder_url','recorder_name_id','auction_backend'])
    w.writeheader()
    w.writerows(results)

print(f"\nTotal counties: {len(results)}")
