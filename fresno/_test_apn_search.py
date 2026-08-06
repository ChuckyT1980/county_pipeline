import sys, re
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
import httpx

c = httpx.Client(base_url="https://fresnocountyca-web.tylerhost.net", timeout=25,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"},
    follow_redirects=True)
c.get("/web/user/disclaimer")
c.post("/web/user/disclaimer")
c.get("/web/search/DOCSEARCH377S5")

AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

def search(apn):
    payload = {
        "field_ParcelID": apn,
        "field_selfservice_documentTypes-containsInput": "Contains Any",
        "field_selfservice_documentTypes": "",
    }
    r2 = c.post("/web/searchPost/DOCSEARCH377S5", data=payload, headers=AJAX)
    r3 = c.get("/web/searchResults/DOCSEARCH377S5", headers=AJAX, params={"page": 1})
    t = re.sub(r"<[^>]+>", " ", r3.text)
    t = re.sub(r"\s+", " ", t)
    return r2.status_code, r3.status_code, t[:300]

for apn in ["090-101-15", "09010115", "39440007", "312-584-19S"]:
    s1, s2, t = search(apn)
    print(f"APN={apn}: post={s1} results={s2}")
    print("   ", t)
    print()
