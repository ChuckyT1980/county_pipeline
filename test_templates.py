import requests
from bs4 import BeautifulSoup
import json
import re

# We need the JSESSIONID from eagleweb_state.json
with open('tax_pipeline/eagleweb_state.json', 'r') as f:
    state = json.load(f)

cookies = {c['name']: c['value'] for c in state['cookies']}

for i in range(1, 10):
    url = f"https://recordsearch.tehama.gov/web/search/DOCSEARCH4S{i}"
    r = requests.get(url, cookies=cookies)
    
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Look for labels
        labels = [l.text.strip() for l in soup.find_all('label')]
        
        print(f"--- DOCSEARCH4S{i} ---")
        if labels:
            print("Labels:", ", ".join(labels))
        else:
            print("Title:", soup.title.string if soup.title else "No title")
    else:
        print(f"--- DOCSEARCH4S{i} --- Status: {r.status_code}")
