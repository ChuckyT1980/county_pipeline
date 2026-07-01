import pdfplumber
import csv
import requests
import io
import re

URL = "https://www.tehama.gov/wp-content/uploads/2025/06/June-8th-LEGAL-PUBLICATION-2025-Notice-of-Property-Tax-Delinquency-and-Impending-Default.pdf"

# Download PDF into memory
response = requests.get(URL)
pdf_file = io.BytesIO(response.content)

records = []
current_default_year = ""

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect section headers like "PROPERTY TAX DEFAULTED ON JULY 1, 2017"
            year_match = re.search(r'DEFAULTED ON JULY 1,\s*(\d{4})', line, re.IGNORECASE)
            if year_match:
                current_default_year = year_match.group(1)
                continue

            # Match APN pattern: ###-###-###-000
            # Note: Amount is separated by a space in pdfplumber output
            apn_match = re.match(r'^(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+?)\s+([\d,]+\.\d{2})$', line)
            if apn_match:
                apn = apn_match.group(1)
                name = apn_match.group(2).strip()
                amount = apn_match.group(3).replace(',', '')
                records.append({
                    "apn": apn,
                    "name_address_raw": name,
                    "amount_due": amount,
                    "default_year": current_default_year
                })
            elif records and not re.match(r'^\d{3}-\d{3}-\d{3}-\d{3}', line) and not "PROPERTY TAX DEFAULTED" in line and not "ASSESSMENTS AND OTHER CHARGES" in line:
                # Append extra address/name lines to the last record
                records[-1]["name_address_raw"] += " | " + line

# Write CSV
with open("tehama_tax_default_leads.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["apn", "name_address_raw", "amount_due", "default_year"])
    writer.writeheader()
    writer.writerows(records)

print(f"Done. {len(records)} records written to tehama_tax_default_leads.csv")
