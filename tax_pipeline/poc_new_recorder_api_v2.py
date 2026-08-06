"""
POC v2: Use the DOCSEARCH481S1 page normally — type MORRIS, hit search, capture API calls.
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

    raw_dump = {'responses': []}

    def collect_response(resp):
        url = resp.url
        # Capture any JSON API response
        content_type = resp.headers.get('content-type', '')
        if 'json' in content_type or ('recorder.buttecounty.net/web/' in url 
            and not any(ext in url for ext in ['.css', '.js', '.png', '.jpg', '.gif', '.ico', '.woff', '.svg', 'resources/'])):
            try:
                body = resp.text()
                if 'json' in content_type or len(body) < 50000:
                    raw_dump['responses'].append({
                        'url': url,
                        'status': resp.status,
                        'content_type': content_type,
                        'body': body[:50000]
                    })
                    if len(body) < 10000:
                        print('\n=== %d %s [%s] ===' % (resp.status, url[:120], content_type[:40]))
                        print(body[:2000])
            except:
                pass

    page.on('response', collect_response)

    # Load the page
    print('=== LOADING PAGE ===')
    page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    print('URL:', page.url)
    print('Title:', page.title())

    # If disclaimer, try alternate approach
    if 'disclaimer' in page.url.lower():
        print('\n=== ACCEPT DISCLAIMER ===')
        # Check what's on the page
        html = page.content()
        print('Has form:', '<form' in html)
        print('Has accept:', 'accept' in html.lower()[:2000])
        
        # Try clicking the only button
        btns = page.query_selector_all('button, input[type=submit], a')
        print('Buttons:', len(btns))
        for b in btns:
            text = b.inner_text() or b.get_attribute('value') or ''
            print('  <%s> text="%s"' % (b.evaluate('el => el.tagName'), text.strip()[:30]))
        
        # Submit the form directly
        form = page.query_selector('form')
        if form:
            page.evaluate('() => { document.querySelector("form").submit(); }')
            page.wait_for_timeout(5000)
            page.wait_for_load_state('networkidle')
            print('After form submit URL:', page.url)

    # If still on disclaimer, try Privacy/Disclaimer page differently
    if 'disclaimer' in page.url.lower():
        # The Tyler portal usually has a disclaimer with a checkbox or button
        # Try clicking the Accept button via JavaScript
        page.evaluate('''() => {
            // Find and click any button with accept/agree/continue text
            const btns = document.querySelectorAll('button, input[type=submit], a');
            for (const b of btns) {
                const t = (b.innerText || b.value || '').toLowerCase();
                if (t.includes('accept') || t.includes('agree') || t.includes('continue')) {
                    b.click();
                    return;
                }
            }
        }''')
        page.wait_for_timeout(3000)
        page.wait_for_load_state('networkidle')
        print('After click URL:', page.url)

    # Navigate to DOCSEARCH481S1 if needed
    if 'DOCSEARCH481S1' not in page.url:
        print('\n=== NAVIGATE TO DOCSEARCH481S1 ===')
        page.goto('https://recorder.buttecounty.net/web/search/DOCSEARCH481S1', timeout=30000)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(3000)
        print('URL:', page.url)

    # Now interact with the search page
    print('\n=== PAGE CONTENT ===')
    body = page.evaluate('() => document.body.innerText')
    print(body[:2000])

    # Find search input and type MORRIS
    print('\n=== TYPING MORRIS INTO SEARCH ===')
    # Look for search fields
    inputs = page.query_selector_all('input[type=text], input[type=search], textarea')
    print('Text inputs:', len(inputs))
    for inp in inputs:
        id_ = inp.get_attribute('id') or ''
        name = inp.get_attribute('name') or ''
        placeholder = inp.get_attribute('placeholder') or ''
        print('  id="%s" name="%s" placeholder="%s"' % (id_, name, placeholder))

    # Also look for party name search field specifically
    party = page.query_selector('input[name*=arty], input[id*=arty], input[name*=Name], input[id*=Name]')
    if party:
        print('Party field found:', party.get_attribute('id') or party.get_attribute('name'))
    else:
        # Just use the first text input
        search_fields = page.query_selector_all('#SearchName, #partyName, #searchName, input[placeholder*=Name], input[placeholder*=Search]')
        for sf in search_fields:
            print('Search field:', sf.get_attribute('id') or sf.get_attribute('name'))
        
        # If there's a text input, use the first one
        text_inputs = page.query_selector_all('input[type=text]')
        if text_inputs:
            target = text_inputs[0]
            target.fill('MORRIS')
            page.wait_for_timeout(1000)
            print('Filled MORRIS into:', target.get_attribute('id') or 'unknown')

    # Hit search button
    print('\n=== CLICKING SEARCH ===')
    search_btn = page.query_selector('#searchButton, button:has-text("Search"), input[type=submit][value*=earch]')
    if search_btn:
        search_btn.click()
    else:
        # Try submitting the form
        form = page.query_selector('form')
        if form:
            page.evaluate('() => { document.querySelector("form").submit(); }')
    
    page.wait_for_timeout(5000)
    page.wait_for_load_state('networkidle')

    # Check if there's a search result list or table
    print('\n=== SEARCH RESULTS ===')
    lis = page.query_selector_all('li[class*=ui-li], tr, .ss-result, [data-role=listview] li')
    print('Results items:', len(lis))
    for li in lis[:5]:
        print(' ', li.inner_text()[:200])

    # Check for results container
    body_after = page.evaluate('() => document.body.innerText')
    print('\nBody after search:', body_after[:2000])

    # Try to find the API URL from the JS by checking what URL patterns are used
    print('\n=== SEARCHING FOR API PATTERNS IN PAGE ===')
    html = page.content()
    patterns = ['BothNames', 'NameSearch', 'party', 'PartySearch', 'DOCSEARCH', 'searchParty', 
                'searchName', 'api/', 'rest/', 'getParties', 'findParties']
    for p in patterns:
        idx = html.find(p)
        if idx >= 0:
            snippet = html[max(0,idx-80):idx+150]
            print('  %s at %d: ...%s...' % (p, idx, snippet[:200]))

    # Also check JavaScript files for API paths
    print('\n=== CHECKING SELF-SERVICE JS FOR API PATTERNS ===')
    js_sources = []
    for script in page.query_selector_all('script[src]'):
        src = script.get_attribute('src')
        if src and 'self.service' in src:
            js_sources.append(src)
    
    for js_path in js_sources:
        full_url = 'https://recorder.buttecounty.net' + js_path if js_path.startswith('/') else js_path
        try:
            resp = page.evaluate('''async (url) => {
                const r = await fetch(url);
                return await r.text();
            }''', full_url)
            # Search for API endpoints
            for p in ['BothNames', 'NameSearch', 'party', 'PartySearch', 'searchParty', 
                      'searchName', 'api/', 'rest/', 'getParties', 'findParties', 'nameSearch',
                      'ByName', 'ByParty', 'DOCSEARCH']:
                idx = resp.find(p)
                if idx >= 0:
                    snippet = resp[max(0,idx-100):idx+200]
                    print('  [%s] %s: ...%s...' % (js_path.split('/')[-1], p, snippet[:300]))
        except Exception as e:
            print('  Error fetching %s: %s' % (js_path, e))

    # Write the dump
    with open(BASE + '/poc_recorder_api_dump.json', 'w') as f:
        json.dump(raw_dump, f, indent=2, default=str)
    print('\nRaw dump: poc_recorder_api_dump.json')

    browser.close()
