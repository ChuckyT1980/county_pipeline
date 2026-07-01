import requests
from bs4 import BeautifulSoup
import json

with open('tax_pipeline/eagleweb_state.json', 'r') as f:
    state = json.load(f)
cookies = {c['name']: c['value'] for c in state['cookies']}

for i in range(1, 6):
    url = f"https://recordsearch.tehama.gov/web/search/DOCSEARCH4S{i}"
    r = requests.get(url, cookies=cookies)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    print(f"--- DOCSEARCH4S{i} ---")
    for input_tag in soup.find_all('input'):
        print(input_tag.get('id'), input_tag.get('name'), input_tag.get('placeholder'))
