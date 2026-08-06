"""Probe Tehama Tyler portal: which search IDs work, what fields each has."""
import re, sys
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
from tyler_recorder_client import TylerRecorderClient, CountyConfig
from bs4 import BeautifulSoup

BASE = "https://recordsearch.tehama.gov"

def probe(search_id: str):
    cfg = CountyConfig(
        county="tehama", base_url=BASE,
        name_search_id="DOCSEARCH4S1", doc_search_id=search_id,
        ajax_headers_required=True, doc_number_transform=None,
    )
    client = TylerRecorderClient(cfg)
    try:
        client._init_session()
        resp = client.client.get(f"/web/search/{search_id}")
        final = str(resp.url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        inputs = [(i.get("name") or i.get("id")) for i in soup.select("input")]
        fields = [i for i in inputs if i and ("field" in i or "ID" in i)]
        buttons = [b.get("id") for b in soup.select("button")]
        rows = len(soup.select("li.ss-search-row"))
        print(f"\n=== {search_id} ===")
        print(f"final_url: {final}")
        print(f"title: {title}")
        print(f"fields({len(fields)}): {sorted(set(fields))}")
        print(f"buttons: {buttons}")
        print(f"result_rows: {rows}")
        print(f"is_disclaimer: {'disclaimer' in final.lower() or 'Disclaimer' in title}")
    finally:
        client.close()

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    ids = ["DOCSEARCH4S1", "DOCSEARCH4S2", "DOCSEARCH4S3"] if which == "all" else [which]
    for sid in ids:
        probe(sid)
