"""
probe_tehama_doc_formats.py — Diagnostic probe for Tehama recorder document number wire formats.
"""
from tyler_recorder_client import TylerRecorderClient, CountyConfig

TEHAMA = CountyConfig('tehama', 'https://recordsearch.tehama.gov', 'DOCSEARCH4S1', 'DOCSEARCH4S2')
client = TylerRecorderClient(TEHAMA)
client._init_session()
client._visit_search_page('DOCSEARCH4S2')

test_formats = [
    '2022R000326',
    '2022000326',
    '2022-000326',
    '2022R00326',
    '202200326',
    '2026R006490',
    '2026006490',
]

for fmt in test_formats:
    client.client.post(
        'https://recordsearch.tehama.gov/web/searchPost/DOCSEARCH4S2',
        data={'field_DocumentNumberID': fmt, 'field_BookPageID_DOT_Volume': '', 'field_BookPageID_DOT_Page': ''},
        headers=client._ajax_headers()
    )
    res = client.client.get(
        'https://recordsearch.tehama.gov/web/searchResults/DOCSEARCH4S2?page=1',
        headers=client._ajax_headers()
    )
    has_row = 'ss-search-row' in res.text
    has_no_results = 'no results' in res.text.lower()
    print(f"Format {fmt:15s} -> len: {len(res.text):6d} | has_row: {has_row} | has_no_results: {has_no_results}")
