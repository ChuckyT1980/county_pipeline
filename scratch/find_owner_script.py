"""Find the full script containing v.Owner"""
import requests
from bs4 import BeautifulSoup
import re

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

url = 'https://common2.mptsweb.com/MBC/shasta/tax/main/070050072000/2025/0000'
resp = session.get(url, timeout=15)
html = resp.text

# Find the script containing v.Owner
soup = BeautifulSoup(html, 'html.parser')
scripts = soup.find_all('script')
for s in scripts:
    txt = s.string or ''
    if 'v.Owner' in txt:
        print('=== Script with v.Owner ===')
        # Print lines around v.Owner
        lines = txt.split('\n')
        for i, line in enumerate(lines):
            if 'v.Owner' in line:
                start = max(0, i-5)
                end = min(len(lines), i+5)
                for j in range(start, end):
                    print('  %d: %s' % (j, lines[j][:200]))
                print('---')
        
        # Also look for what format the cardresultsTemplate expects
        if 'cardresultsTemplate' in txt:
            match = re.search(r'cardresultsTemplate\s*=\s*([^;]+)', txt)
            if match:
                print('\nTemplate definition:')
                print(match.group(1)[:500])
        
        # Look for the format function
        if '.format(' in txt:
            format_matches = re.finditer(r'\.format\(([^)]+)\)', txt)
            for fm in format_matches:
                if 'Owner' in fm.group(1):
                    print('\nFormat call with Owner:', fm.group(0))
