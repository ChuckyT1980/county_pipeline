import csv
from collections import Counter

p = r'data\counties\fresno\roll.csv'
rows = list(csv.DictReader(open(p, encoding='utf-8-sig')))
print('total:', len(rows))

# What does NON_RENEWAL_YEAR / CONTRACT_YEAR look like?
for f in ['NON_RENEWAL_YEAR', 'CONTRACT_YEAR', 'USE_PRIMARY']:
    c = Counter(str(r.get(f) or '')[:6] for r in rows)
    print(f'\n{f} top values:')
    for k, v in c.most_common(8):
        print(f'  {k!r}: {v:,}')

# Where do non-renewal years >= 2019 occur? Those are 5+ year tax defaults.
nry = [r for r in rows if (r.get('NON_RENEWAL_YEAR') or '').strip() not in ('', '0')]
print('\nparcels with NON_RENEWAL_YEAR set:', len(nry))
c = Counter(r['NON_RENEWAL_YEAR'] for r in nry)
for k, v in sorted(c.items(), reverse=True)[:12]:
    print(f'  {k}: {v:,}')

# parcels with default markers in description
markers = ['tax default', 'power to sell', 'delinquent', 'defaulted']
hits = [r for r in rows if any(m in str(r.get('WORD_DESCRIPTION') or '').lower() for m in markers)]
print('\nWORD_DESCRIPTION default markers:', len(hits))
for r in hits[:10]:
    print(f'  {r["APN"]} {str(r["WORD_DESCRIPTION"])[:60]}')

# what does a top-155 look like? show one
top = [r for r in rows if r.get('NON_RENEWAL_YEAR') or (r.get('CONTRACT_YEAR') or '').strip() not in ('', '0')]
print('\nsample with any non-renewal/contract year:')
for r in top[:5]:
    print(f'  {r["APN"]} nry={r.get("NON_RENEWAL_YEAR")} cy={r.get("CONTRACT_YEAR")} '
          f'name={str(r.get("NAME1"))[:20]} desc={str(r.get("WORD_DESCRIPTION"))[:40]}')
