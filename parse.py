import json

with open('tehama_live_test.json') as f:
    data = json.load(f)

for d in data:
    try:
        parsed = json.loads(d['data'])
        rows = parsed.get('Table', {}).get('Row', [])
        # Sometimes Row is a dict if there's only 1 item
        if isinstance(rows, dict):
            rows = [rows]
        count = len(rows)
        print(f"Query: {d['query']:<10} Field: {d['field']:<12} Count: {count}")
        if count > 0:
            print(f"  Sample APN: {rows[0].get('FeeParcel', 'N/A')}")
    except Exception as e:
        print(f"Error parsing {d['query']} {d['field']}: {e}")
