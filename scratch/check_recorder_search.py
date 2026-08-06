import requests
from bs4 import BeautifulSoup
import re

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Step 1: Get the disclaimer page
url = 'https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1'
resp = session.get(url, timeout=15)
print('Step 1 status:', resp.status_code)

# Find the disclaimer form
soup = BeautifulSoup(resp.text, 'html.parser')

# Look for any form, buttons, or POST targets
forms = soup.find_all('form')
print('Forms:', len(forms))
for f in forms:
    action = f.get('action', '')
    method = f.get('method', 'GET')
    print('  action=%s method=%s' % (action, method))
    for inp in f.find_all(['input', 'button']):
        name = inp.get('name', '')
        val = inp.get('value', '')
        id_ = inp.get('id', '')
        print('    %s (id=%s) = %s' % (name, id_, val[:50] if val else ''))

# Find the "I Accept" button
accept = soup.find('button', id='submitDisclaimerAccept') or soup.find('input', id='submitDisclaimerAccept')
if accept:
    print('\nFound accept button:', accept)
else:
    # Search for any accept
    for t in ['accept', 'agree', 'continue', 'submit']:
        btn = soup.find(lambda tag: tag.name in ['button', 'input', 'a'] and t in (tag.get('id', '') + tag.get('value', '') + tag.get_text()).lower())
        if btn:
            print('Found %s element:', t, btn)

# Print the page structure to understand the form
print('\n=== Page structure ===')
for tag in soup.find_all(['form', 'div', 'section']):
    id_ = tag.get('id', '')
    class_ = tag.get('class', '')
    if id_ or class_:
        print('  %s id=%s class=%s' % (tag.name, str(id_)[:40], str(class_)[:60]))
