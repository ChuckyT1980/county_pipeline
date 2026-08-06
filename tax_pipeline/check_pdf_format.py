import fitz, os, sys

base = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"
pdfs = sorted([f for f in os.listdir(base) if f.startswith("pdf_") and f.endswith(".pdf")])

out = open(os.path.join(base, "pdf_formats.txt"), "w", encoding="utf-8")

for name in ["pdf_jun2006.pdf", "pdf_jun2010.pdf", "pdf_jun2016.pdf", "pdf_jun2021.pdf", "pdf_jun2024.pdf", "pdf_sep2024_reoffer.pdf", "pdf_sep2021.pdf", "pdf_sep2017.pdf"]:
    path = os.path.join(base, name)
    doc = fitz.open(path)
    text = ""
    for page in doc:
        text += page.get_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out.write(f"\n=== {name} ({doc.page_count} pages, {len(lines)} lines) ===\n")
    for l in lines[:30]:
        out.write(f"  {l}\n")
    out.write(f"  ... ({len(lines)} total lines)\n")
    for l in lines[-10:]:
        out.write(f"  {l}\n")
    doc.close()
out.close()
print("Done. Check pdf_formats.txt")
