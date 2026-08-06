import requests, json, warnings
warnings.filterwarnings('ignore')
u = 'https://gis.shastacounty.gov/arcgis/rest/services/OpenData/Parcels/MapServer/0'
d = requests.get(u, params={'f':'json'}, timeout=20, verify=False).json()
print('fields:', len(d.get('fields', [])))
for f in d['fields'][:45]:
    print(f"  {f['name']:30s} {f['type']}")
