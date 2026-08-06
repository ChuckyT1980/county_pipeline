import requests, re, csv, time
from bs4 import BeautifulSoup

def normalize_parcel(raw):
    return re.sub(r"[^0-9]", "", raw.strip())

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

s = list(csv.DictReader(open('tax_pipeline/shasta_MASTER_leads_with_liens.csv', newline='', encoding='utf-8-sig')))

results = []
for i, row in enumerate(s):
    apn = row['APN']
    parcel = normalize_parcel(apn)
    roll_cat = row.get('roll_cat', 'CS').strip()
    roll_type = "S" if roll_cat.endswith("S") else "U"
    
    url = f"https://apps.mptsweb.com/TaxBillv2/Default.aspx?County=shasta&Asmt={parcel}&TaxYear=2025&RollCat={roll_cat}&RollYr=&RollType={roll_type}&DisplayType=HTML"
    
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract values by element IDs
        def get_span_val(id_val):
            el = soup.find(id=id_val)
            if el:
                return el.get_text(strip=True)
            return ""
        
        cur_land = get_span_val("CurMarketLandValue") or get_span_val("PriMarketLandValue")
        cur_improv = get_span_val("CurStructuralImprValue") or get_span_val("PriStructuralImprValue")
        pers_prop = get_span_val("CurPersPropValue") or get_span_val("PriPersPropValue")
        acres = get_span_val("ACRES")
        situs = get_span_val("ParcelDescription")
        
        # Calculate net taxable value: land + improvements - exemptions
        # Or find the NET TAXABLE VALUE display
        # The net taxable value is in a row following NETVALUEDESC
        net_val = ""
        net_desc = soup.find(id="NETVALUEDESC")
        if net_desc:
            parent_row = net_desc.find_parent(class_="row-5")
            if parent_row:
                spans = parent_row.find_all("span", class_="col")
                for sp in spans:
                    txt = sp.get_text(strip=True).replace(',', '').replace('$', '')
                    if txt.isdigit():
                        net_val = txt
                        break
        
        # Also try looking at the value spans after NETVALUEDESC's row
        if not net_val:
            # Look for a span that has the taxable value
            val_span = soup.find(id="NETTAXABLEVALUE")
            if val_span:
                net_val = val_span.get_text(strip=True)
        
        # If still not found, try to parse from the text structure
        # The row-5 class after the description contains: span(desc) span(prior_yr) span(cur_yr) span(billed)
        # Find the row that follows NETVALUEDESC
        if not net_val:
            all_rows = soup.find_all("div", class_="row-5")
            found_net = False
            for row_div in all_rows:
                spans = row_div.find_all("span", class_="col")
                texts = [s.get_text(strip=True) for s in spans]
                if any("NET TAXABLE VALUE" in t.upper() for t in texts):
                    found_net = True
                    continue
                if found_net:
                    for t in texts:
                        cleaned = t.replace(',', '').replace('$', '')
                        if cleaned.isdigit():
                            net_val = t
                            break
                    break
        
        results.append({
            'apn': apn,
            'apn_clean': parcel,
            'roll_cat': roll_cat,
            'cur_land_value': cur_land,
            'cur_improvement_value': cur_improv,
            'pers_prop_value': pers_prop,
            'net_taxable_value': net_val,
            'acres': acres,
            'situs_address': situs,
            'source_url': url,
        })
        
        if (i+1) % 25 == 0:
            found = sum(1 for r in results if r.get('net_taxable_value'))
            print(f"Progress: {i+1}/{len(s)} (net values found so far: {found})")
        
        time.sleep(0.5)
            
    except Exception as e:
        results.append({'apn': apn, 'apn_clean': parcel, 'roll_cat': roll_cat, 'error': str(e)})
        print(f"  ERROR {apn}: {e}")

print(f"\nDone: {len(results)} leads")
found_net = sum(1 for r in results if r.get('net_taxable_value'))
found_land = sum(1 for r in results if r.get('cur_land_value') and r['cur_land_value'] != '0')
found_acres = sum(1 for r in results if r.get('acres'))
print(f"Net taxable value: {found_net}/{len(results)}")
print(f"Land value (non-zero): {found_land}/{len(results)}")
print(f"Acres: {found_acres}/{len(results)}")

for r in results[:5]:
    print(f"  {r['apn']}: land={r['cur_land_value']} improv={r['cur_improvement_value']} net={r['net_taxable_value']} acres={r['acres']}")

with open('shasta_assessed_values.csv', 'w', newline='', encoding='utf-8') as f:
    fields = ['apn','apn_clean','roll_cat','cur_land_value','cur_improvement_value','pers_prop_value','net_taxable_value','acres','situs_address','source_url','error']
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(results)
print("Saved to shasta_assessed_values.csv")
