#!/usr/bin/env python3
"""
stage5_pdf_merge.py
Extracts APN + owner name from the June 2025 legal publication PDF
and merges against your live pipeline CSV on APN.
Output: tehama_final_leads.csv (complete — verified tax data + legal owner name)
"""

import re
import csv
import pdfplumber

PDF_PATH    = "June-8th-LEGAL-PUBLICATION-2025-Notice-of-Property-Tax-Delinquency-and-Impending-Default.pdf"
PIPELINE_CSV = "tehama_audit_20260627_024321.csv"          # Using the full 7,743-row audit file
OUTPUT_CSV   = "tehama_final_leads.csv"

APN_PATTERN = re.compile(r'(\d{3}-\d{3}-\d{3}-\d{3})')

def normalize_apn(apn: str) -> str:
    """Strip dashes for consistent matching."""
    return apn.replace("-", "").strip().zfill(12)

def extract_pdf_records(pdf_path: str) -> dict:
    """
    Parse the legal publication PDF.
    Returns dict keyed by normalized APN:
      { '064050032000': {'apn': '064-050-032-000', 'assessee': '...', 'situs': '...', 'amt_due': '...',  'default_year': '...'} }
    """
    records = {}
    current_default_year = ""

    # Regex to detect default year headers
    default_year_re = re.compile(
        r'PROPERTY TAX DEFAULTED ON JULY 1[,\s]+(\d{4})', re.IGNORECASE
    )
    # Regex for a data line: APN + assessee + optional address + amount
    # Format from PDF: 064-050-032-000 LEMMAFAMREVOCTROF2000 4,410.81
    data_re = re.compile(
        r'(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+?)\s+([\d,]+\.\d{2})\s*$'
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")
            for line in lines:
                # Check for default year header
                yr_match = default_year_re.search(line)
                if yr_match:
                    current_default_year = yr_match.group(1)
                    continue

                # Check for data line
                d_match = data_re.search(line)
                if d_match:
                    apn_raw   = d_match.group(1).strip()
                    assessee  = d_match.group(2).strip()
                    amt_due   = d_match.group(3).strip()
                    norm_apn  = normalize_apn(apn_raw)

                    # Situs address: often on same line after assessee before amount
                    # or embedded in assessee field — try to split on digit pattern
                    situs = ""
                    addr_match = re.search(
                        r'(\d+\s+[A-Z0-9\s]+(?:RD|DR|AVE|ST|LN|WAY|HWY|BLVD|CT|PL|CIR|TR|LOOP|BEND)[A-Z0-9\s]*)',
                        assessee, re.IGNORECASE
                    )
                    if addr_match:
                        situs    = addr_match.group(1).strip()
                        assessee = assessee.replace(situs, "").strip()

                    records[norm_apn] = {
                        "apn_pdf":          apn_raw,
                        "assessee_name":    assessee,
                        "situs_pdf":        situs,
                        "amt_due_june2025": amt_due,
                        "default_year":     current_default_year,
                        "pdf_source":       "Tehama_LegalPublication_June2025",
                    }

    print(f"[PDF] Extracted {len(records)} records from legal publication.")
    return records


def merge_with_pipeline(pdf_records: dict, pipeline_csv: str, output_csv: str):
    """
    Join PDF records (owner names) into pipeline CSV on APN.
    Adds assessee_name, default_year, amt_due_june2025 to each lead.
    """
    with open(pipeline_csv, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    matched = 0
    unmatched = 0
    enriched = []

    for lead in leads:
        # Normalize the APN from pipeline (may be feeparcel or asmt field)
        raw_apn = lead.get("fee_parcel", lead.get("feeparcel", lead.get("asmt", "")))
        norm    = normalize_apn(raw_apn)

        pdf_rec = pdf_records.get(norm, {})

        enriched.append({
            **lead,
            "assessee_name":    pdf_rec.get("assessee_name", ""),
            "default_year":     pdf_rec.get("default_year", ""),
            "amt_due_june2025": pdf_rec.get("amt_due_june2025", ""),
            "situs_pdf":        pdf_rec.get("situs_pdf", ""),
            "pdf_source":       pdf_rec.get("pdf_source", ""),
            "name_matched":     "YES" if pdf_rec else "NO",
        })

        if pdf_rec:
            matched += 1
        else:
            unmatched += 1

    # Write output
    fieldnames = list(enriched[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched)

    print(f"[Merge] Matched:   {matched}")
    print(f"[Merge] Unmatched: {unmatched}")
    print(f"[Merge] Output:    {output_csv}")
    return enriched


if __name__ == "__main__":
    pdf_records = extract_pdf_records(PDF_PATH)
    merge_with_pipeline(pdf_records, PIPELINE_CSV, OUTPUT_CSV)
