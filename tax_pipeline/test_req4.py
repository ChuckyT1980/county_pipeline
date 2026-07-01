import requests
import json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest'
})

# Get home page to get JSESSIONID
s.get("https://recordsearch.tehama.gov/web")

# We can find the submit form action or just try to accept the session disclaimer
url_accept = "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE"
r = s.get(url_accept)
print("Length of result:", len(r.text))

if "Federal Tax Lien" in r.text or "Deed of Trust" in r.text:
    print("Found docs!")
else:
    print("Could not find docs.")
    
# Let's save the file to look at it
with open("test_req4_out.html", "w", encoding="utf-8") as f:
    f.write(r.text)
