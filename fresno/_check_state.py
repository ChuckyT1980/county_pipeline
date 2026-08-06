import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.state import StateStore

store = StateStore(CountyConfig.load('fresno'))
print('parcels in state:', store.count())
print()
for g in store.gaps():
    if g['missing'] > 0:
        print(f"  {g['field']:16s} via {g['source']:10s} prio={g['priority']}  missing={g['missing']:,}")
print()
print('next action:', store.next_action())
store.close()
