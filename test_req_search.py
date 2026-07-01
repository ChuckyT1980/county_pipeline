import requests, json, bs4

with open('tax_pipeline/eagleweb_state.json', 'r') as f:
    state = json.load(f)

cookies = {}
for c in state['cookies']:
    cookies[c['name']] = c['value']

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://recordsearch.tehama.gov',
    'Referer': 'https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1'
})
requests.utils.add_dict_to_cookiejar(s.cookies, cookies)

payload = {
    'field_BothNamesID': 'SOTO JOSE',
    'action': 'Search'
}

res = s.post('https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1', data=payload)
soup = bs4.BeautifulSoup(res.text, 'html.parser')

print('Results:')
for li in soup.find_all('li', class_='ui-li-static'):
    if '•' in li.text:
        print(li.text.strip()[:100].replace('\n', ' '))
