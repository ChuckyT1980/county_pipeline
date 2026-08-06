import sys, tempfile, csv, os
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.assessor import _pull_arcgis

cfg = CountyConfig.load('fresno')
cfg.assessor.where = "APN IN ('09010115','46308201','47822105','00712018','05332206')"
out = tempfile.mktemp(suffix='.csv')
_pull_arcgis(cfg, out)
rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
print('smoke rows:', len(rows))
print('columns:', len(rows[0]))
print('first APN:', rows[0]['APN'], '| owner:', rows[0]['NAME1'], '| value:', rows[0]['TOTAL_ASSESSED_VALUE'])
os.remove(out)
