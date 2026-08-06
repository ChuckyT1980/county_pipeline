"""
POC Final: Hit suggest endpoint for real Butte auction owners,
dump raw JSON row, compare to current recorder_chain schema.
"""
import json, time
from playwright.sync_api import sync_playwright

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"

# Owners from our enriched auction data — mix of individuals, LLCs, trusts
TEST_OWNERS = [
    'MORRIS',       # heavy hitter, 21 mortgages
    'YADIRA',       # LLC with big equity
    'ABADIR',       # multiple parcels, fed tax liens
    'MACIAS',       # high-value
    'HAYES',        # high score
    'DEWSNUP',      # Kyle — individual
    'BAUMBERGER',   # living trust
    'LAKE MADRONE', # trust name
    'GRIDLEY BUSINESS TRUST',
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1280, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = context.new_page()

    raw_dump = {'suggest_results': {}, 'search_attempts': {}}

    # Step 1: Establish session
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

    # Step 2: Hit suggest endpoint for each owner
    print('=== SUGGEST ENDPOINT RESULTS ===')
    print('Endpoint: GET /web/search/suggest/BothNamesID?searchText=...&maxValues=1000')
    print()

    all_suggestions = {}
    for owner in TEST_OWNERS:
        result = page.evaluate('''async (name) => {
            const resp = await fetch('/web/search/suggest/BothNamesID?searchText=' + encodeURIComponent(name) + '&maxValues=1000', {
                credentials: 'include',
                headers: {'Accept': 'application/json'}
            });
            const text = await resp.text();
            let json = null;
            try { json = JSON.parse(text); } catch(e) {}
            return {status: resp.status, body: text, json: json};
        }''', owner)

        print('--- %s (status %d) ---' % (owner, result['status']))
        if result['json'] and isinstance(result['json'], list):
            items = result['json']
            print('  Total suggestions: %d' % len(items))
            # Filter for exact matches or close matches
            exact = [s for s in items if s.upper().startswith(owner.upper())]
            print('  Starting with "%s": %d' % (owner, len(exact)))
            for s in exact[:10]:
                print('    "%s"' % s)
            if len(exact) > 10:
                print('    ... and %d more' % (len(exact) - 10))
            all_suggestions[owner] = items
        else:
            print('  Raw:', result['body'][:300])
            all_suggestions[owner] = result['body']

    # Step 3: Try the suggest endpoint with longer/more specific names
    print('\n=== SPECIFIC NAME SUGGESTS ===')
    specific_names = [
        'MORRIS ELIZABETH',
        'HAYES KEVIN',
        'DEWSNUP KYLE',
        'YADIRA PROPERTIES',
        'ABADIR PERRY',
    ]
    for name in specific_names:
        result = page.evaluate('''async (name) => {
            const resp = await fetch('/web/search/suggest/BothNamesID?searchText=' + encodeURIComponent(name) + '&maxValues=1000', {
                credentials: 'include',
                headers: {'Accept': 'application/json'}
            });
            const text = await resp.text();
            let json = null;
            try { json = JSON.parse(text); } catch(e) {}
            return {status: resp.status, body: text, json: json};
        }''', name)

        print('--- %s (status %d) ---' % (name, result['status']))
        if result['json'] and isinstance(result['json'], list):
            # Filter for relevant matches
            items = result['json']
            # Show items that contain the search terms
            terms = name.upper().split()
            relevant = [s for s in items if all(t in s.upper() for t in terms)]
            print('  Exactly matching suggestions: %d' % len(relevant))
            for s in relevant[:15]:
                print('    "%s"' % s)
            if len(relevant) > 15:
                print('    ... and %d more' % (len(relevant) - 15))
        else:
            print('  Raw:', result['body'][:300])

    # Step 4: Document the schema/format
    print('\n=== SCHEMA COMPARISON ===')
    print('''
Suggest endpoint returns: JSON array of strings
  - Simple party/owner names as flat strings
  - No typed fields, no IDs, no party type distinction
  - Max 1000 results
  - No pagination metadata

Contrast with our current recorder_chain schema:
  - Structured JSON: {doc_type, grantor, grantee, date, doc_number}
  - Typed fields per document type
  - Party roles (grantor/grantee) distinguished
  - Full document metadata

Gap: suggest endpoint is autocomplete-only.
SearchPost (POST /web/searchPost/DOCSEARCH481S1) returns full HTML
with document details — requires authenticated session to access.
''')

    # Step 5: Attempt searchPost with form submission (to see login wall)
    print('\n=== SEARCHPOST AUTH TEST ===')
    search_input = page.query_selector('#field_BothNamesID')
    if search_input:
        search_input.fill('MORRIS ELIZABETH')
        page.wait_for_timeout(2000)
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)

    # Try submitting form programmatically
    result = page.evaluate('''async () => {
        const form = document.querySelector('form');
        if (!form) return 'no form';
        const fd = new FormData(form);
        fd.set('field_BothNamesID', 'MORRIS ELIZABETH');
        const resp = await fetch(form.action, {
            method: 'POST',
            credentials: 'include',
            body: new URLSearchParams(fd)
        });
        return {status: resp.status, body: await resp.text(), headers: Object.fromEntries(resp.headers)};
    }''')
    print('  Status:', result.get('status'))
    if len(result.get('body', '')) < 500:
        print('  Body:', result['body'])
    else:
        print('  Body (%d chars): %s' % (len(result['body']), result['body'][:500]))
    print('  Content-Type:', result.get('headers', {}).get('content-type', ''))

    # Also hit the searchPost with just the name param directly
    print('\n=== SEARCHPOST DIRECT WITH MINIMAL PARAMS ===')
    for name in ['MORRIS ELIZABETH', 'MORRIS']:
        r = page.evaluate('''async (name) => {
            const resp = await fetch('/web/searchPost/DOCSEARCH481S1', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'field_BothNamesID=' + encodeURIComponent(name)
            });
            return {status: resp.status, body: await resp.text()};
        }''', name)
        print('  field_BothNamesID=%s -> %d' % (name, r['status']))
        print('    Body: %s' % r['body'][:300])

    browser.close()

    # Write the dump
    with open(BASE + '/poc_recorder_api_dump.json', 'w') as f:
        json.dump(raw_dump, f, indent=2, default=str)

    # Write suggestions to dedicated JSON
    with open(BASE + '/poc_suggest_results.json', 'w') as f:
        json.dump(all_suggestions, f, indent=2, default=str)

    print('\nDumps written.')
