import sys, re
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

c = httpx.Client(base_url="https://fresnocountyca-web.tylerhost.net", timeout=25,
    headers={"User-Agent": UA}, follow_redirects=True)
r = c.get("/web/user/disclaimer")
print("GET disclaimer:", r.status_code)
r = c.post("/web/user/disclaimer")
print("POST disclaimer:", r.status_code, "body:", repr(r.text[:60]))
print("cookies:", [ck.name for ck in c.cookies.jar])
r = c.get("/web/search/DOCSEARCH377S5")
print("GET search:", r.status_code)

payload = {
    "field_ParcelID": "090-101-15",
    "field_selfservice_documentTypes-containsInput": "Contains Any",
    "field_selfservice_documentTypes": "",
}
r2 = c.post("/web/searchPost/DOCSEARCH377S5", data=payload, headers=AJAX)
print("POST searchPost:", r2.status_code, "len", len(r2.text), "preview:", r2.text[:80].replace("\n"," "))
r3 = c.get("/web/searchResults/DOCSEARCH377S5", headers=AJAX, params={"page": 1, "_": "1785520255944"})
t = re.sub(r"<[^>]+>", " ", r3.text); t = re.sub(r"\s+", " ", t)
print("GET searchResults:", r3.status_code)
print(t[:400])
