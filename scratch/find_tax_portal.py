"""Find and explore Shasta County tax payment portal"""
import requests, re

# Find the main county site
r = requests.get('https://www.co.shasta.ca.us/index/departments/county-departments/treasurer-tax-collector', 
                  timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
print(f"Status: {r.status_code}")
text = r.text

# Find all links
for m in re.findall(r'href=[\'"]([^\'"]*)[\'"]', text):
    m = m.strip()
    if any(kw in m.lower() for kw in ['pay', 'tax', 'portal', 'property', 'treasurer', 'mpay', 'megabyte']):
        print(f"  LINK: {m}")
