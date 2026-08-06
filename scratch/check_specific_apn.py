"""Check if specific MASTER APNs appear in any PDF"""
import pdfplumber, re

PDFS = [
    r"C:\Users\chuck\Downloads\june_2025_legal_publication_-_impending_power_to_sell.pdf",
    r"C:\Users\chuck\Downloads\first_year_delinquent_list_2025_-_page_1.pdf",
    r"C:\Users\chuck\Downloads\fist_year_delinquent_llist_2025_-_page_2.pdf",
    r"C:\Users\chuck\Downloads\december_2025_-_notice_of_public_auction.pdf",
    r"C:\Users\chuck\Downloads\notice_of_excess_proceeds_for_2025_auction.pdf",
]

targets = ['070-050-072-000', '064-100-031-000', '018-600-041-000', '102-150-007-000']
targets_norm = [re.sub(r'\D', '', t) for t in targets]

for path in PDFS:
    name = path.split('\\')[-1]
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                for target, tnorm in zip(targets, targets_norm):
                    if tnorm in re.sub(r'\D', '', text):
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        for j, line in enumerate(lines):
                            if tnorm in re.sub(r'\D', '', line):
                                print('%s p%d: %s' % (name, i+1, line[:300]))
    except FileNotFoundError:
        print('%s: NOT FOUND' % name)
