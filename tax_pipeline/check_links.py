import fitz

doc = fitz.open('Tehama_Top_5_Distressed_Property_Intelligence_Report_WITH_LINKS.pdf')
for page_num in range(len(doc)):
    page = doc[page_num]
    links = page.get_links()
    print(f'Page {page_num+1}: {len(links)} links')
    for link in links:
        r = link['from']
        print(f'  rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f}) uri={link["uri"]}')
doc.close()

print()

doc2 = fitz.open('Tehama_35_Distressed_Property_Intelligence_Report_WITH_LINKS.pdf')
for page_num in range(len(doc2)):
    page = doc2[page_num]
    links = page.get_links()
    print(f'Page {page_num+1}: {len(links)} links')
    for link in links[:3]:
        r = link['from']
        print(f'  rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f}) uri={link["uri"]}')
    if len(links) > 3:
        print(f'  ... and {len(links)-3} more')
doc2.close()
