import csv

files = ['tehama_gold_leads.csv', 'tehama_pdf_direct_leads.csv']
all_rows = []
fieldnames = []

for fp in files:
    try:
        with open(fp, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Add new fieldnames if they aren't in the list yet
            for fn in reader.fieldnames:
                if fn not in fieldnames:
                    fieldnames.append(fn)
                    
            for row in reader:
                # tehama_pdf_direct_leads has live_total_balance
                # tehama_gold_leads has total_stacked_balance
                bal = row.get('live_total_balance')
                if not bal:
                    bal = row.get('total_stacked_balance', '0')
                    
                status = row.get('live_paid_status', '')
                if not status:
                    status = row.get('asmt_status', '')
                
                try:
                    bal_float = float(bal)
                except ValueError:
                    bal_float = 0.0
                    
                if status.upper() not in ['PAID', 'ERROR'] and bal_float > 0:
                    # normalize the balance column so sorting works
                    row['live_total_balance'] = str(bal_float)
                    all_rows.append(row)
    except Exception as e:
        print(f'Skipping {fp}: {e}')

all_rows.sort(key=lambda r: float(r.get('live_total_balance','0') or 0), reverse=True)

with open('tehama_MASTER_leads.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(all_rows)

print(f'MASTER leads: {len(all_rows)} active delinquent named leads')
print('Top 5:')
for r in all_rows[:5]:
    print(f"  {r.get('assessee_name','')[:35]} | bal=${r.get('live_total_balance')} | {r.get('apn_pdf', row.get('fee_parcel', ''))}")
