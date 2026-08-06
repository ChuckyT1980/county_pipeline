import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from tyler_recorder_client import TylerRecorderClient, CountyConfig as TylerCC

cfg = CountyConfig.load('fresno')
tcfg = TylerCC(
    county=cfg.county,
    base_url=cfg.recorder.base_url,
    name_search_id=cfg.recorder.name_search_id,
    doc_search_id=cfg.recorder.doc_search_id,
    apn_search_id=cfg.recorder.apn_search_id or "",
    ajax_headers_required=cfg.recorder.ajax_headers_required,
    doc_number_transform=cfg.recorder.doc_number_transform,
)
client = TylerRecorderClient(tcfg)
client.submit_apn_search('09010115')
import time
time.sleep(2)
resp = client.get_results(page=1, search_type='apn')
html = client._last_html if hasattr(client, '_last_html') else ''
print('resp rows:', len(resp[0]))
# dump raw html to file
import requests
# replicate: fetch the results page raw
r = client.client.get(f"/web/searchResults/{tcfg.apn_search_id}",
                      headers=client._ajax_headers(),
                      params={"page": 1, "_": int(time.time()*1000)})
open(r'fresno\_results_raw.html', 'w', encoding='utf-8').write(r.text)
print('saved raw html', len(r.text), 'bytes')
# print first row snippet
idx = r.text.find('ss-search-row')
print(r.text[idx:idx+900])
client.close()
