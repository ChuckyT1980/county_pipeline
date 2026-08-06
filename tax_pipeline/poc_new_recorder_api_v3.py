"""
POC v3: Correctly fill field_BothNamesID, hit searchPost, dump JSON.
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
        if 'json' in content_type or ('searchPost' in url or 'BothNames' in url or 'DOCSEARCH' in url):
            try:
                body = resp.text()
                if 'json' in content_type or len(body) < 100000:
                    raw_dump['responses'].append({
                        'url': url,
                        'status': resp.status,
                        'content_type': content_type,
                        'body': body[:100000]
                    })
                    if 'searchPost' in url:
                        print('\n=== SEARCH RESPONSE (%d) %s ===' % (resp.status, url[:100]))
                        try:
                            j = json.loads(body)
                            print(json.dumps(j, indent=2)[:4000])
                        except:
                            print(body[:2000])
            except:
                pass

    page.on('response', collect_response)

    # Load DOCSEARCH481S1
    print('=== LOADING DOCSEARCH481S1 ===')
    page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)

    # Accept disclaimer if present
    if 'disclaimer' in page.url.lower():
        print('Accepting disclaimer...')
        btn = page.query_selector('button:has-text("I Accept")')
        if btn:
            btn.click()
            page.wait_for_timeout(3000)
            page.wait_for_load_state('networkidle')
            print('URL after accept:', page.url)
        
        # Navigate back to search
        page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        print('URL:', page.url)

    # Check if we need to log in
    body = page.evaluate('() => document.body.innerText')
    if 'log in' in body.lower() or 'login' in body.lower():
        print('Login required:', body[:500])
        # Try to proceed as guest - some Tyler portals allow guest search
        # Look for a way to search without login
    
    # Find the search input
    search_input = page.query_selector('#field_BothNamesID')
    if not search_input:
        search_input = page.query_selector('input[id*=BothNames]')
    
    if search_input:
        print('\n=== FILLING SEARCH: MORRIS ===')
        # Use the cblist auto-complete pattern if needed
        # First try clicking to activate
        search_input.click()
        page.wait_for_timeout(500)
        
        # Type the name character by character (for autocomplete)
        search_input.fill('MORRIS')
        page.wait_for_timeout(1000)
        
        # Check what was actually entered
        entered = page.evaluate('() => document.getElementById("field_BothNamesID").value')
        print('Input value:', repr(entered))
    else:
        print('Search input not found!')

    # Click search button
    print('\n=== CLICKING SEARCH ===')
    search_btn = page.query_selector('button:has-text("Search"), input[value*="Search"], #searchButton, a:has-text("Search")')
    if search_btn:
        print('Found search button:', search_btn.inner_text()[:30] or '')
        search_btn.click()
    else:
        # Try the form submit
        page.evaluate('''() => {
            const form = document.querySelector('form');
            if (form) form.submit();
        }''')

    page.wait_for_timeout(5000)
    page.wait_for_load_state('networkidle')

    # Check results
    print('\n=== RESULTS AFTER SEARCH ===')
    lis = page.query_selector_all('li[class*=ui-li]')
    print('List items:', len(lis))
    for li in lis[:10]:
        text = li.inner_text()
        if text.strip():
            print(' ', text[:200])

    # Try to get the raw POST data
    print('\n=== TRYING DIRECT API CALL ===')
    # Get the cookies/session
    cookies = context.cookies()
    cookie_str = '; '.join(['%s=%s' % (c['name'], c['value']) for c in cookies])
    print('Cookies:', cookie_str[:200])

    # Try the searchPost endpoint directly
    result = page.evaluate('''async () => {
        const formData = new FormData();
        formData.append('field_BothNamesID', 'MORRIS');
        formData.append('search', 'Search');
        
        const resp = await fetch('/web/searchPost/DOCSEARCH481S1', {
            method: 'POST',
            credentials: 'include',
            body: new URLSearchParams({
                'field_BothNamesID': 'MORRIS',
                'search': 'Search'
            })
        });
        const text = await resp.text();
        let json = null;
        try { json = JSON.parse(text); } catch(e) {}
        return {status: resp.status, body: text, json: json};
    }''')

    print('Direct API call status:', result['status'])
    if result['json']:
        j = result['json']
        print('Keys:', list(j.keys()) if isinstance(j, dict) else type(j).__name__)
        print(json.dumps(j, indent=2)[:5000])
    else:
        print('Raw:', result['body'][:2000])

    # Also try with includeParty parameter or different structure
    # Tyler searchPost sometimes returns JSON with doctypes, parties, searchResults
    print('\n=== DIFFERENT QUERY FORMATS ===')

    # Try with standard payload
    for payload in [
        {'field_BothNamesID': 'MORRIS', 'search': 'Search'},
        {'field_BothNamesID': 'MORRIS', 'action': 'search', 'searchType': 'name'},
        {'Name': 'MORRIS', 'search': 'Search'},
        {'searchText': 'MORRIS', 'searchType': 'name'},
    ]:
        params = '&'.join(['%s=%s' % (k, v) for k, v in payload.items()])
        r = page.evaluate('''async (params) => {
            const resp = await fetch('/web/searchPost/DOCSEARCH481S1', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: params
            });
            const text = await resp.text();
            return {status: resp.status, body: text};
        }''', params)
        print('  %s -> %d %s' % (params, r['status'], r['body'][:200]))

    browser.close()

    with open(BASE + '/poc_recorder_api_dump.json', 'w') as f:
        json.dump(raw_dump, f, indent=2, default=str)
    print('\nDump: poc_recorder_api_dump.json')
