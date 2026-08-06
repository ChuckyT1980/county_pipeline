import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.recorder import pull_recorder_for_apns

cfg = CountyConfig.load('fresno')
apns = ['09010115', '05332206', '00712018', '46308201']
pull_recorder_for_apns(cfg, apns)
