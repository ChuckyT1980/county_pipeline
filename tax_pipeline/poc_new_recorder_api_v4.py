"""
POC v4: Capture autocomplete API + submit form properly.
"""
import json, time
from playwright.sync_api import sync_playwright

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1280, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = context.new_page()

    raw_dump = {'responses': [], 'search_results': None}

    def collect_response(resp):
        url = resp.url
        content_type = resp.headers.get('content-type', '')
        if 'json' in content_type or 'searchPost' in url or 'BothNames' in url or 'DOCSEARCH' in url:
            try:
                body = resp.text()
                if len(body) < 200000:
                    raw_dump['responses'].append({
                        'url': url,
                        'status': resp.status,
                        'content_type': content_type,
                        'body': body[:100000]
                    })
                    short_url = url.replace('https://recorder.buttecounty.net', '')
                    if 'json' in content_type:
                        print('\n=== JSON %d %s ===' % (resp.status, short_url))
                        try:
                            j = json.loads(body)
                            if isinstance(j, list):
                                print('  [%d items]' % len(j))
                                if j:
                                    print('  First:', json.dumps(j[0], indent=2)[:600])
                                    print('  Keys:', list(j[0].keys()) if isinstance(j[0], dict) else 'scalar')
                            elif isinstance(j, dict):
                                print('  keys:', list(j.keys()))
                                if 'documents' in j:
                                    print('  documents: [%d]' % len(j['documents']))
                                if 'parties' in j:
                                    print('  parties: [%d]' % len(j['parties']))
                                if 'searchResults' in j:
                                    print('  searchResults: [%d]' % len(j['searchResults']))
                                for k, v in j.items():
                                    if isinstance(v, list) and k not in ('documents', 'parties', 'searchResults'):
                                        print('    %s: [%d]' % (k, len(v)))
                                        if v and isinstance(v[0], dict):
                                            print('      keys:', list(v[0].keys()))
                            print(json.dumps(j, indent=2)[:2000])
                        except:
                            print('  (not JSON) %s' % body[:500])
                    elif 'searchPost' in url:
                        print('\n=== SEARCHPOST %d %s ===' % (resp.status, short_url))
                        print(body[:2000])
            except:
                pass

    page.on('response', collect_response)

    # Load
    print('=== LOADING DOCSEARCH481S1 ===')
    page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)

    if 'disclaimer' in page.url.lower():
        btn = page.query_selector('button:has-text("I Accept")')
        if btn:
            btn.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state('networkidle')
        page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)

    # Type MORRIS slowly to trigger autocomplete API calls
    print('\n=== TYPING MORRIS (letter by letter for autocomplete) ===')
    search_input = page.query_selector('#field_BothNamesID')
    if search_input:
        search_input.click()
        # Type one character at a time so we see autocomplete API calls
        for char in 'MORRIS':
            search_input.type(char, delay=200)
            page.wait_for_timeout(300)
        
        page.wait_for_timeout(2000)  # Wait for autocomplete to settle
        
        entered = page.evaluate('() => document.getElementById("field_BothNamesID").value')
        print('Input value:', repr(entered))

    # Dismiss autocomplete by pressing Escape
    print('\n=== DISMISSING AUTOCOMPLETE ===')
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    # Now click Search (the autocomplete overlay is gone)
    print('\n=== CLICKING SEARCH ===')
    search_btn = page.query_selector('button:has-text("Search")')
    if search_btn:
        search_btn.click()
        page.wait_for_timeout(5000)
        page.wait_for_load_state('networkidle')
    else:
        page.evaluate('() => document.querySelector("form").requestSubmit()')
        page.wait_for_timeout(5000)
        page.wait_for_load_state('networkidle')

    # Check results
    print('\n=== RESULTS ===')
    lis = page.query_selector_all('li[class*=ui-li]')
    print('List items:', len(lis))
    for li in lis[:15]:
        text = li.inner_text()
        if text.strip() and 'Name Search' not in text and 'Recorder' not in text:
            print(' ', text[:250])

    # Also look for any data tables
    tables = page.query_selector_all('table')
    print('Tables:', len(tables))

    body = page.evaluate('() => document.body.innerText')
    print('\nBody snippet:', body[500:2000])

    # Check if we need login
    if 'Please log in' in body or 'Log in' in body[:500]:
        print('\n*** LOGIN REQUIRED - search may work for logged-in users only ***')
        
        # But try the autocomplete API directly
        print('\n=== TRYING AUTOCOMPLETE API DIRECTLY ===')
        # The autocomplete endpoint is likely something like:
        for endpoint in [
            '/web/search/DOCSEARCH481S1/BothNamesID',
            '/web/search/DOCSEARCH481S1/BothNames',
            '/web/search/DOCSEARCH481S1/searchText',
            '/web/api/search/DOCSEARCH481S1/BothNamesID',
            '/web/autocomplete/BothNamesID',
            '/web/api/autocomplete/BothNamesID',
        ]:
            r = page.evaluate('''async (url) => {
                try {
                    const resp = await fetch(url + '?searchText=MORRIS', {credentials: 'include'});
                    return {status: resp.status, body: await resp.text()};
                } catch(e) {
                    return {status: -1, body: str(e)};
                }
            }''', endpoint)
            if r['status'] == 200:
                print('  %s -> 200: %s' % (endpoint, r['body'][:300]))
            else:
                print('  %s -> %d' % (endpoint, r['status']))

    browser.close()
    with open(BASE + '/poc_recorder_api_dump.json', 'w') as f:
        json.dump(raw_dump, f, indent=2, default=str)
    print('\nDump: poc_recorder_api_dump.json')
