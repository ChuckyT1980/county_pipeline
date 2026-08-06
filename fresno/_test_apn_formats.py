import sys, re, json
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
AJAX = {
    "ajaxrequest": "true",
    "x-requested-with": "XMLHttpRequest",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "referer": "https://fresnocountyca-web.tylerhost.net/web/search/DOCSEARCH377S5",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
}

def search(apn):
    c = httpx.Client(base_url="https://fresnocountyca-web.tylerhost.net", timeout=25,
        headers={"User-Agent": UA}, follow_redirects=True)
    c.get("/web/user/disclaimer")
    c.post("/web/user/disclaimer")
    c.get("/web/search/DOCSEARCH377S5")
    payload = {
        "field_ParcelID": apn,
        "field_selfservice_documentTypes-containsInput": "Contains Any",
        "field_selfservice_documentTypes": "",
    }
    r2 = c.post("/web/searchPost/DOCSEARCH377S5", data=payload, headers=AJAX)
    r3 = c.get("/web/searchResults/DOCSEARCH377S5", headers=AJAX, params={"page": 1, "_": "1785520255944"})
    t = re.sub(r"<[^>]+>", " ", r3.text)
    t = re.sub(r"\s+", " ", t)
    return r2.text[:120], t[:220]

variants = ["09010115", "090-101-15", "090-101-15-000", "090-101-15-000-0",
            "46308201", "463-082-01", "08018018S", "080-180-18S"]
for v in variants:
    post, res = search(v)
    print(f"APN={v!r}")
    print("  post:", post)
    print("  res: ", res)
    print()
