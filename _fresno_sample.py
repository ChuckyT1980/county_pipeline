import sys, sqlite3
sys.path.insert(0, '.')
from core.county import CountyConfig
from tyler_recorder_client import TylerRecorderClient, CountyConfig as TCC

db = sqlite3.connect('data/counties/fresno/state.sqlite')
apns = [r[0] for r in db.execute(
    "SELECT apn FROM parcels WHERE owner_known=0 AND owner_checked=0 "
    "ORDER BY RANDOM() LIMIT 12")]

cfg = CountyConfig.load('fresno')
tc = TCC(county='fresno', base_url=cfg.recorder.base_url,
         name_search_id=cfg.recorder.name_search_id,
         doc_search_id=cfg.recorder.doc_search_id,
         apn_search_id=cfg.recorder.apn_search_id,
         ajax_headers_required=cfg.recorder.ajax_headers_required,
         doc_number_transform=cfg.recorder.doc_number_transform)
c = TylerRecorderClient(tc)

hits = 0
for apn in apns:
    try:
        c.submit_apn_search(apn)
        pr, tr = c.get_results(page=1, search_type='apn')
        if pr:
            hits += 1
        types = sorted({r.doc_type for r in pr})
        print(f'{apn}: {len(pr)} docs types={types}')
    except Exception as e:
        print(f'{apn}: FAIL {str(e)[:60]}')
c.close()
print(f'\nhit rate: {hits}/{len(apns)}')
