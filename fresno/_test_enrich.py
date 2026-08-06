import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.assessor import _arcgis_apn_enrich

cfg = CountyConfig.load('fresno')
apns = ['09010115', '05332206', '00712018', '46308201', '00119007']
recs = _arcgis_apn_enrich(cfg, apns)
print('records returned:', len(recs))
for r in recs:
    print(f"  {r['APN']} | {str(r['NAME1'])[:22]:22s} | "
          f"mail={str(r['ADDRESS1'])[:20]:20s} | val={r['TOTAL_ASSESSED_VALUE']}")
