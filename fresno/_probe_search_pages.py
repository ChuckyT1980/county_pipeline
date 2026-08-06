import sys, re
sys.path.insert(0, '.')
from tyler_recorder_client import TylerRecorderClient, CountyConfig

cfg = CountyConfig(
    county="fresno",
    base_url="https://fresnocountyca-web.tylerhost.net",
    name_search_id="DOCSEARCH377S1",
    doc_search_id="DOCSEARCH377S2",
    apn_search_id="DOCSEARCH377S5",
    ajax_headers_required=True,
    doc_number_transform=None,
)
client = TylerRecorderClient(cfg)
try:
    for sid in ("DOCSEARCH377S1", "DOCSEARCH377S2", "DOCSEARCH377S5"):
        client._visit_search_page(sid)
        resp = client.client.get(f"/web/search/{sid}")
        html = resp.text
        inputs = sorted(set(re.findall(r'name="([^"]+)"', html)))
        opts = re.findall(r'<option[^>]*value="([^"]+)"[^>]*>([^<]*)</option>', html)
        print(f"=== {sid} (len={len(html)}) ===")
        print("  inputs:", inputs)
        print("  doc-type options:")
        for v, label in opts:
            if "deed" in v.lower() or "deed" in label.lower() or "tax" in v.lower() or "tax" in label.lower():
                print(f"    {v!r} -> {label!r}")
        print()
finally:
    client.close()
