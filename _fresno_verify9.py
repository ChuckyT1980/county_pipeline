import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from tyler_recorder_client import TylerRecorderClient, CountyConfig as TCC

cfg = CountyConfig.load('fresno')
tc = TCC(county='fresno', base_url=cfg.recorder.base_url,
         name_search_id=cfg.recorder.name_search_id,
         doc_search_id=cfg.recorder.doc_search_id,
         apn_search_id=cfg.recorder.apn_search_id,
         ajax_headers_required=cfg.recorder.ajax_headers_required,
         doc_number_transform=cfg.recorder.doc_number_transform)
c = TylerRecorderClient(tc)

apns = ['00402025P', '00402027P', '00402030P', '00712018', '05332206',
        '06327014M', '09010115', '13615535', '46308201']
for apn in apns:
    try:
        c.submit_apn_search(apn)
        pr, tr = c.get_results(page=1, search_type='apn')
        print(f'=== {apn}: {len(pr)} docs')
        for r in pr:
            print(f'   {r.doc_type} {r.doc_number} {r.recording_date} | '
                  f'{"/".join(r.grantors)[:50]} -> {"/".join(r.grantees)[:50]}')
    except Exception as e:
        print(f'{apn} FAIL: {str(e)[:100]}')
c.close()
