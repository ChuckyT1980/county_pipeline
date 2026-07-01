import requests

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
print("1. Getting homepage")
r = s.get("https://recordsearch.tehama.gov/web")

# Typically Tyler posts to a generic /web/ endpoint with a specific JSF/ASP.net hidden input, or just sets a cookie.
print("Cookies:", s.cookies.get_dict())

# Let's try searching directly, maybe it doesn't even need the disclaimer if we hit the search endpoint with GET?
print("2. Search SOTO")
r_search = s.get("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE")
if "SOTO" in r_search.text or "JOSE" in r_search.text:
    print("Found names in search response!")
else:
    print("No names found. Must need disclaimer.")
    
# Try posting to accept
print("3. Try to accept disclaimer")
r_acc = s.post("https://recordsearch.tehama.gov/web/disclaimer/accept")
r_search2 = s.get("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE")
if "SOTO" in r_search2.text:
    print("Found names after accept!")
else:
    print("Still no names.")
