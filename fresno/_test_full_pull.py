import requests, json
E = 'https://gisprod10.co.fresno.ca.us/server/rest/services/FC_PARCEL_SELECT/MapServer/0/query'
where = "APN IS NOT NULL AND APN <> ''"
r = requests.get(E, params={'where': where, 'returnCountOnly': 'true', 'f': 'json'}, timeout=30)
print('APN-populated count:', r.json().get('count'))
r = requests.get(E, params={'where': where, 'outFields': '*', 'resultOffset': 0,
                            'resultRecordCount': 2000, 'returnGeometry': 'false', 'f': 'json'}, timeout=60)
d = r.json()
print('page size returned:', len(d.get('features', [])))
a = d['features'][0]['attributes']
print('keys:', len(a))
for k in ['APN', 'NAME1', 'ADDRESS1', 'SITEADDRESS1', 'TOTAL_ASSESSED_VALUE',
          'INSTRUMENT_NUMBER', 'RECORDING_DATE', 'CONTRACT_YEAR', 'NON_RENEWAL_YEAR',
          'USE_PRIMARY', 'WORD_DESCRIPTION', 'SOURCE_LAYER']:
    print(f'  {k}: {a.get(k)}')
