import csv

with open('tehama_final_leads.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    matches = [row for row in reader if row.get('name_matched') == 'YES']
    fieldnames = reader.fieldnames

if matches:
    with open('tehama_gold_leads.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    
    print("Gold Leads Extracted:")
    print("-" * 50)
    for row in matches:
        print(f"APN:     {row.get('fee_parcel')}")
        print(f"Owner:   {row.get('assessee_name')}")
        print(f"Address: {row.get('situs_pdf', 'No address')} (or {row.get('address')})")
        print(f"Debt:    ${row.get('total_stacked_balance')} (Amount Due June: {row.get('amt_due_june2025')})")
        print("-" * 50)
else:
    print("No gold leads found.")
