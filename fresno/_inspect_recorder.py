import csv
from collections import Counter

rows = list(csv.DictReader(open(r'data\counties\fresno\recorder_docs.csv', encoding='utf-8-sig')))
c = Counter(r['doc_type'] for r in rows)
print('doc types:')
for k, v in c.most_common():
    print(f'  {k}: {v}')
print()
for r in rows[:12]:
    print(f"  {r['apn']} | {r['recording_date']} | {str(r['doc_type'])[:40]:40s} | {str(r['doc_number'])[:16]}")
