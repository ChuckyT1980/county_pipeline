"""Explore the new Butte recorder portal API endpoints."""
import re, json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    requests_log = []
    page.on('request', lambda req: requests_log.append({
        'url': req.url, 'method': req.method,
        'headers': dict(req.headers), 'post_data': req.post_data
    }) if 'recorder.buttecounty' in req.url else None)

    responses = []
    page.on('response', lambda resp: responses.append({
        'url': resp.url, 'status': resp.status,
    }) if 'recorder.buttecounty' in resp.url else None)

    page.goto('https://recorder.buttecounty.net/web/search/', timeout=30000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    print('=== PAGE LOADED ===')
    print('Title:', page.title())
    print('URL:', page.url)

    print('\n=== REQUESTS TO RECORDER ===')
    for r in requests_log:
        short = r['url'][:150]
        print('  %s %s' % (r['method'], short))
        if r['post_data']:
            try:
                j = json.loads(r['post_data'])
                print('    POST data keys:', list(j.keys()) if isinstance(j, dict) else 'array')
            except:
                print('    POST: %s' % r['post_data'][:200])

    print('\n=== RESPONSES ===')
    for r in responses:
        print('  %d %s' % (r['status'], r['url'][:150]))

    print('\n=== API URLS IN PAGE ===')
    html = page.content()
    for m in re.finditer(r'https?://recorder\.buttecounty\.net[^"\'<\s]+', html):
        print('  %s' % m.group())

    browser.close()
