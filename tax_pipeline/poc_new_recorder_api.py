"""
POC: Hit new Butte recorder endpoints for MORRIS owner search.
1. Accept disclaimer -> establish session
2. GET BothNamesID?searchText=MORRIS -> returns matching parties
3. Use party ID to hit DOCSEARCH481S1 for documents
4. Dump raw JSON rows
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

    api_calls = []
    raw_dump = {'requests': [], 'responses': []}

    page.on('request', lambda req: api_calls.append({
        'url': req.url, 'method': req.method,
        'post_data': req.post_data,
        'timestamp': time.time()
    }) if 'recorder.buttecounty.net/web/' in req.url and not any(ext in req.url for ext in ['.css', '.js', '.png', '.jpg', '.gif', '.ico', '.woff', '.svg']) else None)

    def collect_response(resp):
        url = resp.url
        if 'recorder.buttecounty.net/web/' in url and not any(ext in url for ext in ['.css', '.js', '.png', '.jpg', '.gif', '.ico', '.woff', '.svg', 'resources/']):
            try:
                body = resp.text()
                entry = {'url': url, 'status': resp.status, 'body': body[:10000]}
                raw_dump['responses'].append(entry)
                if len(body) < 8000:
                    print('\n=== %s %s ===' % (resp.status, url[:110]))
                    # Try to parse as JSON and pretty-print
                    try:
                        j = json.loads(body)
                        if isinstance(j, list):
                            print('  [%d items]' % len(j))
                            if j:
                                print('  First:', json.dumps(j[0], indent=2)[:600])
                                print('  Keys:', list(j[0].keys()) if isinstance(j[0], dict) else 'scalar')
                                if len(j) > 1:
                                    print('  Last:', json.dumps(j[-1], indent=2)[:600])
                        elif isinstance(j, dict):
                            print('  keys:', list(j.keys()))
                            for k, v in j.items():
                                if isinstance(v, list):
                                    print('    %s: [%d items]' % (k, len(v)))
                                    if v and isinstance(v[0], dict):
                                        print('      keys:', list(v[0].keys()))
                                elif isinstance(v, dict):
                                    print('    %s: dict %s' % (k, list(v.keys())))
                                else:
                                    print('    %s: %s' % (k, str(v)[:200]))
                        else:
                            print('  ', str(j)[:500])
                    except json.JSONDecodeError:
                        print('  Raw (%d): %s' % (len(body), body[:1200]))
            except:
                pass

    page.on('response', collect_response)

    # Step 1: Load and accept disclaimer
    print('=== STEP 1: Load page ===')
    page.goto('https://recorder.buttecounty.net/web/search/', timeout=30000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    print('URL:', page.url)

    if 'disclaimer' in page.url.lower():
        print('=== STEP 1b: Accept disclaimer ===')
        # Try clicking accept
        for sel in ['input[type=submit]', 'button:has-text("Accept")', 'button:has-text("continue")',
                     'a:has-text("Accept")', 'button:has-text("I Accept")', '#accept']:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_timeout(3000)
                page.wait_for_load_state('networkidle')
                print('Clicked:', sel, '->', page.url)
                break
        else:
            body = page.evaluate('() => document.body.innerText')
            print('Disclaimer body:', body[:800])

    # Step 2: Navigate to DOCSEARCH481S1
    print('\n=== STEP 2: DOCSEARCH481S1 ===')
    page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
    page.wait_for_load_state('networkidle') 
    page.wait_for_timeout(2000)
    print('URL:', page.url)
    print('Title:', page.title())

    # Step 3: BothNamesID search for MORRIS
    print('\n=== STEP 3: BothNamesID?searchText=MORRIS ===')
    name_result = page.evaluate('''async () => {
        const resp = await fetch('/web/search/DOCSEARCH481S1/BothNamesID?searchText=MORRIS', {
            credentials: 'include',
            headers: {'Accept': 'application/json, text/plain, */*'}
        });
        const text = await resp.text();
        let json = null;
        try { json = JSON.parse(text); } catch(e) {}
        return {status: resp.status, body: text, json: json};
    }''')

    print('Status:', name_result['status'])
    if name_result['json']:
        data = name_result['json']
        if isinstance(data, list):
            print('Items:', len(data))
            for item in data:
                print('  ', json.dumps(item, indent=2)[:400])
        elif isinstance(data, dict):
            print('Keys:', list(data.keys()))
            print(json.dumps(data, indent=2)[:2000])
    else:
        print('Raw:', name_result['body'][:1500])

    # Step 4: Try DOCSEARCH481S1 with party param
    print('\n=== STEP 4: DOCSEARCH481S1 direct (maybe GET with query) ===')
    search_result = page.evaluate('''async () => {
        const resp = await fetch('/web/search/DOCSEARCH481S1', {
            credentials: 'include',
            headers: {'Accept': 'application/json, text/plain, */*'}
        });
        const text = await resp.text();
        return {status: resp.status, body: text};
    }''')
    print('Status:', search_result['status'])
    print('Raw:', search_result['body'][:1500])

    # Step 5: Try searching with a POST
    print('\n=== STEP 5: POST to DOCSEARCH481S1 with MORRIS ===')
    post_result = page.evaluate('''async () => {
        const form = new FormData();
        form.append('searchText', 'MORRIS');
        form.append('searchType', 'name');
        const resp = await fetch('/web/search/DOCSEARCH481S1', {
            method: 'POST',
            credentials: 'include',
            body: form
        });
        const text = await resp.text();
        return {status: resp.status, body: text};
    }''')
    print('Status:', post_result['status'])
    try:
        j = json.loads(post_result['body'])
        print('JSON:', json.dumps(j, indent=2)[:2000])
    except:
        print('Raw:', post_result['body'][:1500])

    # Step 6: Look for an ID from BothNamesID and search by it
    print('\n=== STEP 6: Extract party ID from BothNamesID result ===')
    if name_result['json']:
        data = name_result['json']
        if isinstance(data, list) and data:
            party_id = data[0].get('id') or data[0].get('partyID') or data[0].get('partyId') or data[0].get('ID')
            print('First item keys:', list(data[0].keys()))
            print('Potential party ID:', party_id)
            if party_id:
                doc_result = page.evaluate('''async (pid) => {
                    const resp = await fetch('/web/search/DOCSEARCH481S1?partyId=' + encodeURIComponent(pid), {
                        credentials: 'include',
                        headers: {'Accept': 'application/json'}
                    });
                    return {status: resp.status, body: await resp.text()};
                }''', party_id)
                print('Doc search by party ID status:', doc_result['status'])
                try:
                    j = json.loads(doc_result['body'])
                    print(json.dumps(j, indent=2)[:2000])
                except:
                    print('Raw:', doc_result['body'][:1500])

    browser.close()

    # Write everything to file
    with open(BASE + '/poc_recorder_api_dump.json', 'w') as f:
        json.dump(raw_dump, f, indent=2, default=str)
    print('\nRaw dump: poc_recorder_api_dump.json')
