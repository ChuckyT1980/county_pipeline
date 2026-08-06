import requests
import re

session = requests.Session()
r = session.get('https://recorderselfservice.shastacounty.gov/web/')
r2 = session.get('https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1')
print('Status 2:', r2.status_code)

match = re.search(r'action="(/web/user/disclaimer[^"]+)"', r2.text)
if match:
    action_url = 'https://recorderselfservice.shastacounty.gov' + match.group(1)
    r3 = session.post(action_url, data={'disclaimer': 'accepted'})
    print('Status 3:', r3.status_code)
    
    r4 = session.get('https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1')
    print('Status 4:', r4.status_code)
    
    with open('shasta_real_search.html', 'w', encoding='utf-8') as f:
        f.write(r4.text)
    print('Saved to shasta_real_search.html')
else:
    print('No disclaimer form found. Is it the search page?')
    with open('shasta_real_search.html', 'w', encoding='utf-8') as f:
        f.write(r2.text)
    print('Saved r2 to shasta_real_search.html')
