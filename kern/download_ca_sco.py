import requests, os
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

# Download CA SCO Property Tax Raw Data 2019-2026
print("Downloading CA SCO Property Tax Raw Data 2019-2026...")
url = "https://bythenumbers.sco.ca.gov/download/cigd-fqva/application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    out = os.path.join(BASE, "ca_sco_property_tax_raw_2019_2026.xlsx")
    total = 0
    with open(out, "wb") as f:
        for chunk in r.iter_content(chunk_size=32768):
            f.write(chunk)
            total += len(chunk)
    print(f"Saved {total:,} bytes -> {out}")
    
    # Read and check sheets
    xl = pd.ExcelFile(out)
    print(f"Sheets: {xl.sheet_names}")
    for sheet in xl.sheet_names[:5]:
        df = xl.parse(sheet)
        print(f"\n  Sheet: {sheet} | Rows: {len(df)} | Cols: {list(df.columns)[:8]}")
        kern = df[df.apply(lambda row: any("kern" in str(v).lower() for v in row), axis=1)]
        if len(kern) > 0:
            print(f"  *** KERN ROWS FOUND: {len(kern)} ***")
            print(kern.head(3).to_string())
else:
    print(f"Download failed: {r.status_code}")

# Property Tax Levies CSV (smaller - check first)
print("\nDownloading Property Tax Levies CSV...")
url2 = "https://bythenumbers.sco.ca.gov/api/v3/views/km92-7amc/export.csv?accessType=DOWNLOAD"
r2 = requests.get(url2, headers=HEADERS, timeout=20)
print(f"Status: {r2.status_code}  Bytes: {len(r2.content)}")
if r2.status_code == 200:
    out2 = os.path.join(BASE, "ca_property_tax_levies.csv")
    with open(out2, "wb") as f:
        f.write(r2.content)
    df2 = pd.read_csv(out2)
    print(f"Rows: {len(df2)}  Cols: {list(df2.columns)}")
    kern2 = df2[df2.apply(lambda row: any("kern" in str(v).lower() for v in row), axis=1)]
    print(f"Kern rows: {len(kern2)}")
    if len(kern2) > 0:
        print(kern2.head(5).to_string())
