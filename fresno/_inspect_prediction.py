import csv
from collections import Counter

p = r'data\counties\fresno\predicted_auction.csv'
rows = list(csv.DictReader(open(p, encoding='utf-8-sig')))
print('scored:', len(rows))
c = Counter(r['score'] for r in rows)
print('score distribution:')
for s in sorted(c, reverse=True):
    print(f'  score {s}: {c[s]:,}')
print()
print('TOP 15 PREDICTED:')
for r in rows[:15]:
    print(f"  {r['score']:>3} {r['apn']:12s} {str(r['name'])[:22]:22s} "
          f"{str(r['situs'])[:24]:24s} {str(r['value'])[:14]:14s} default={str(r['default'])[:28]}")
