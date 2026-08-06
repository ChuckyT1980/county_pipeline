import re
with open('bid4assets_butte_aug2026.html', encoding='utf-8') as f:
    html = f.read()

# Find the download link near "Download Property List"
idx = html.find('Download Property List')
if idx > 0:
    # Look for the nearest <a> tag or onclick handler within 500 chars
    ctx = html[idx:idx+500]
    print('Context:', ctx[:300])
    # Find href
    for m in re.finditer(r'href=[\'"]([^\'"]+)[\'"]', ctx):
        print('\nFound href:', m.group(1))
    # Find onclick
    for m in re.finditer(r'onclick=[\'"]([^\'"]+)[\'"]', ctx):
        print('\nFound onclick:', m.group(1))
    # Find data-url
    for m in re.finditer(r'data-url=[\'"]([^\'"]+)[\'"]', ctx):
        print('\nFound data-url:', m.group(1))
else:
    # Search whole page
    for m in re.finditer(r'[Dd]ownload[^<]*?href=[\'"]([^\'"]+)[\'"]', html):
        print('Download link:', m.group(1))
    # Also find any href with csv/xlsx
    for m in re.finditer(r'href=[\'"]([^\'"]*\.(?:csv|xlsx?|pdf)[^\'"]*)[\'"]', html, re.I):
        print('File link:', m.group(1))
    # Find all links in the page body
    for m in re.finditer(r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>', html):
        txt_after = html[m.end():m.end()+100]
        clean = re.sub(r'<[^>]+>', ' ', txt_after)[:80]
        print('Link: %s -> %s' % (m.group(1), clean.strip()))
