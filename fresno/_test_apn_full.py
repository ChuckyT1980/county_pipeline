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
c.get("/web/user/disclaimer")
c.post("/web/user/disclaimer")
c.get("/web/search/DOCSEARCH377S5")
payload = {
    "field_ParcelID": "09010115",
    "field_selfservice_documentTypes-containsInput": "Contains Any",
    "field_selfservice_documentTypes": "",
}
r2 = c.post("/web/searchPost/DOCSEARCH377S5", data=payload, headers=AJAX)
r3 = c.get("/web/searchResults/DOCSEARCH377S5", headers=AJAX, params={"page": 1, "_": "1785520255944"})
open(r"fresno\_apn_results_full.html", "w", encoding="utf-8").write(r3.text)
print("saved", len(r3.text), "bytes")

# extract the document table region
m = re.search(r"(?:<table.*?</table>)", r3.text, re.S)
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", r3.text))
print(text[:3000])
