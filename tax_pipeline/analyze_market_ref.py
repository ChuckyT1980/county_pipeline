import csv, re, os

parent = r"C:\Users\chuck\Downloads\county_pipeline"

# 1. Properties actually for sale = our market reference
with open(os.path.join(parent, "leads_for_sale.csv")) as f:
    sale = list(csv.DictReader(f))

print(f"Properties for sale: {len(sale)}")

liens_list = []
sig_counts = {}
score_list = []

for row in sale:
    reasons = row.get("Reasons", "")
    score_list.append(float(row.get("SellerIntentScore", 0)))

    # count liens
    m = re.search(r"(\d+)\s*Active\s*Liens?", reasons, re.I)
    if m:
        liens_list.append(int(m.group(1)))

    for sig_name, sig_pattern in [
        ("mortgage", r"Has Mortgage|Mortgage Recorded|mortgage"),
        ("assignment_rents", r"Assignment of Rents|assignment of rents"),
        ("affidavit_death", r"Affidavit of Death|affidavit of death"),
        ("tax_delinquent", r"Late Tax|Tax Delinquent|taxes late|tax delinquency"),
        ("out_of_state", r"Out-of-state|Out.of.state"),
    ]:
        if re.search(sig_pattern, reasons, re.I):
            sig_counts[sig_name] = sig_counts.get(sig_name, 0) + 1

print(f"\n--- Signal distribution on FOR-SALE properties (market reference) ---")
print(f"Liens: {liens_list}")
if liens_list:
    print(f"  avg: {sum(liens_list)/len(liens_list):.1f}, max: {max(liens_list)}, min: {min(liens_list)}")
    # bucket
    for b in [(0,0),(1,2),(3,5),(6,9),(10,99)]:
        cnt = sum(1 for l in liens_list if b[0] <= l <= b[1])
        print(f"  {b[0]}-{b[1]}: {cnt}")

for sig, cnt in sorted(sig_counts.items()):
    print(f"{sig}: {cnt}/{len(sale)} ({cnt/len(sale)*100:.0f}%)")

if score_list:
    print(f"\nCurrent SellerIntentScore on for-sale props:")
    print(f"  range: {min(score_list):.1f} - {max(score_list):.1f}")
    print(f"  avg: {sum(score_list)/len(score_list):.1f}")
    for b in [(0,5),(5,10),(10,20),(20,50),(50,100)]:
        cnt = sum(1 for s in score_list if b[0] <= s < b[1])
        print(f"  {b[0]:.0f}-{b[1]:.0f}: {cnt}")

# 2. Also look at all_seller_intent to see full signal distribution
print(f"\n--- All seller intent data (all counties, all scores) ---")
with open(os.path.join(parent, "all_seller_intent.csv")) as f:
    all_intent = list(csv.DictReader(f))

real = [r for r in all_intent if r.get("apn") != "001-001-001"]
print(f"Total real leads: {len(real)}")

# Signal co-occurrence
multi_signal = 0
liens_only = 0
for row in real:
    reasons = row.get("Reasons", "")
    signals_present = []
    if re.search(r"Active\s*Lien", reasons, re.I): signals_present.append("liens")
    if re.search(r"Has Mortgage|Mortgage Recorded", reasons, re.I): signals_present.append("mortgage")
    if re.search(r"Assignment of Rents", reasons, re.I): signals_present.append("assignment")
    if re.search(r"Affidavit of Death", reasons, re.I): signals_present.append("affidavit")
    if re.search(r"Late|Delinquent|taxes late|tax delinquency", reasons, re.I): signals_present.append("tax")
    if re.search(r"Out.of.state", reasons, re.I): signals_present.append("oos")
    if len(signals_present) >= 3:
        multi_signal += 1
    if len(signals_present) <= 1:
        liens_only += 1

print(f"Properties with 3+ signals: {multi_signal}/{len(real)} ({multi_signal/len(real)*100:.0f}%)")
print(f"Properties with 0-1 signals: {liens_only}/{len(real)} ({liens_only/len(real)*100:.0f}%)")
