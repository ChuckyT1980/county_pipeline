import fitz

for fname in ['Tehama_Top_5_Distressed_Property_Intelligence_Report_WITH_LINKS.pdf',
              'Tehama_35_Distressed_Property_Intelligence_Report_WITH_LINKS.pdf']:
    doc = fitz.open(fname)
    print(f'\n=== {fname} ===')
    print(f'Total pages: {len(doc)}')
    total_links = 0
    for pn in range(len(doc)):
        links = doc[pn].get_links()
        total_links += len(links)
    print(f'Total links: {total_links}')

    # Check page 2 (first lead page) for ASSESSOR text
    if len(doc) > 1:
        p2 = doc[1]
        t2 = p2.get_text('text')
        has_assessor = "ASSESSOR" in t2
        has_clickable = "clickable" in t2
        p2_links = p2.get_links()
        print(f'Page 2: assessor_text={has_assessor} clickable_text={has_clickable} links={len(p2_links)}')
        if p2_links:
            print(f'  First link: {p2_links[0]["uri"]}')
    doc.close()
