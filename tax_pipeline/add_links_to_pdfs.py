#!/usr/bin/env python3
"""
Add visible clickable assessor links to APN numbers in PDFs.
- Blue underlined APN text
- Blue 'VIEW' badge next to each APN
- Link annotation on both the APN and the badge
- Explanatory note at top of page 1
"""
import fitz
import re
import os

blue = (0.15, 0.35, 0.85)
dark_blue = (0.1, 0.2, 0.6)
white = (1, 1, 1)

def add_assessor_links(pdf_path):
    doc = fitz.open(pdf_path)
    link_count = 0
    seen_urls = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        apns = list(set(re.findall(r"\d{3}-\d{3}-\d{3}-\d{3}", text)))

        for apn in apns:
            compact = apn.replace("-", "")
            url = f"https://common1.mptsweb.com/MBC/tehama/tax/main/{compact}/2025/0000"
            if url in seen_urls:
                continue

            rects = page.search_for(apn)
            for rect in rects:
                # Draw a prominent blue underline under the APN
                underline_y = rect.y1 + 1.5
                page.draw_line(
                    fitz.Point(rect.x0, underline_y),
                    fitz.Point(rect.x1, underline_y),
                    color=blue, width=1.2,
                )

                # Link annotation on the APN text itself
                apn_rect = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
                page.insert_link({"kind": fitz.LINK_URI, "uri": url, "from": apn_rect})

                # Add a small "ASSESSOR \u2197" clickable label right after the APN
                label_x = rect.x1 + 4
                label_y = rect.y0
                label_w = page.rect.width - label_x
                if label_w > 60:
                    page.insert_text(
                        fitz.Point(label_x, rect.y1 - 1),
                        "ASSESSOR \u2197",
                        fontsize=7,
                        color=blue,
                    )
                    label_rect = fitz.Rect(label_x, rect.y0 - 1, label_x + 48, rect.y1 + 1)
                    page.insert_link({"kind": fitz.LINK_URI, "uri": url, "from": label_rect})

                link_count += 1
                seen_urls.add(url)

    # Add a note on page 1 footer
    page0 = doc[0]
    pw = page0.rect.width
    note_rect = fitz.Rect(40, page0.rect.height - 50, pw - 40, page0.rect.height - 30)
    page0.draw_rect(note_rect, color=blue, fill=(0.95, 0.97, 1), width=0.5)
    page0.insert_text(
        fitz.Point(44, page0.rect.height - 36),
        "Blue underlined APN numbers and ASSESSOR labels are clickable links to the Tehama County Assessor portal.",
        fontsize=8,
        color=dark_blue,
    )

    base, ext = os.path.splitext(pdf_path)
    out_path = f"{base}_WITH_LINKS{ext}"
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return out_path, link_count


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pdfs = [
        "Tehama_Top_5_Distressed_Property_Intelligence_Report.pdf",
        "Tehama_35_Distressed_Property_Intelligence_Report.pdf",
    ]
    for pdf_name in pdfs:
        path = os.path.join(base_dir, pdf_name)
        if os.path.exists(path):
            out, count = add_assessor_links(path)
            print(f"{pdf_name}: {count} links -> {os.path.basename(out)}")
        else:
            print(f"NOT FOUND: {path}")
