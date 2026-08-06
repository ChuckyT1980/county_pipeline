"""
inspect_tehama_session.py — Test exact disclaimer cookies on Tehama portal.
"""
import httpx

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

with httpx.Client(headers={"User-Agent": ua}, follow_redirects=True) as client:
    client.get("https://recordsearch.tehama.gov/web/user/disclaimer")
    client.post("https://recordsearch.tehama.gov/web/user/disclaimer")
    client.get("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S2")

    # Set disclaimerAccepted=true on domain
    client.cookies.set("disclaimerAccepted", "true", domain="recordsearch.tehama.gov")
    # Also POST disclaimer again after search page visit
    client.post("https://recordsearch.tehama.gov/web/user/disclaimer")

    print("Cookies after post disclaimer:", client.cookies.items())

    ajax_headers = {
        "ajaxrequest": "true",
        "x-requested-with": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    r4 = client.post(
        "https://recordsearch.tehama.gov/web/searchPost/DOCSEARCH4S2",
        data={"field_DocumentNumberID": "2026006490", "field_BookPageID_DOT_Volume": "", "field_BookPageID_DOT_Page": ""},
        headers=ajax_headers
    )
    print("POST /searchPost -> status:", r4.status_code, "final url:", r4.url)

    r5 = client.get("https://recordsearch.tehama.gov/web/searchResults/DOCSEARCH4S2?page=1", headers=ajax_headers)
    print("GET /searchResults -> status:", r5.status_code, "final url:", r5.url, "len:", len(r5.text))
    print("Has ss-search-row:", "ss-search-row" in r5.text)
    print("Has no results:", "no results" in r5.text.lower())
