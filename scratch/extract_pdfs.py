"""Extract owner names from Shasta County PDFs and match to our MASTER leads"""
import pdfplumber, re, json

PDFS = {
    "power_to_sell": r"C:\Users\chuck\Downloads\june_2025_legal_publication_-_impending_power_to_sell.pdf",
    "delinquent_p1": r"C:\Users\chuck\Downloads\first_year_delinquent_list_2025_-_page_1.pdf",
    "delinquent_p2": r"C:\Users\chuck\Downloads\fist_year_delinquent_llist_2025_-_page_2.pdf",
    "auction": r"C:\Users\chuck\Downloads\december_2025_-_notice_of_public_auction.pdf",
    "excess": r"C:\Users\chuck\Downloads\notice_of_excess_proceeds_for_2025_auction.pdf",
}

# APN pattern: 3 digits, dash, 3 digits, dash, 3 digits, dash, 3 digits
APN_RE = re.compile(r'(\d{3}[-.]?\d{3}[-.]?\d{3}[-.]?\d{3})')

def normalize(apn):
    d = re.sub(r'\D', '', apn)
    if len(d) == 12:
        return '%s-%s-%s-%s' % (d[:3], d[3:6], d[6:9], d[9:12])
    return apn

for name, path in PDFS.items():
    print('\n=== %s ===' % name)
    try:
        with pdfplumber.open(path) as pdf:
            print('Pages: %d' % len(pdf.pages))
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Find APNs on this page
                apns_found = 0
                for line in lines:
                    if APN_RE.search(line):
                        apns_found += 1
                
                print('  Page %d: %d lines, ~%d APNs found' % (i+1, len(lines), apns_found))
                
                # Print first 30 lines of page 1
                if i == 0:
                    print('  First 30 lines:')
                    for l in lines[:30]:
                        print('    ' + l[:200])
    except Exception as e:
        print('  ERROR: %s' % e)
