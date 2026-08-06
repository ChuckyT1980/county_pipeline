import csv, os, re, sys

sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline")
from seller_intent_scorer import score_lead

parent = r"C:\Users\chuck\Downloads\county_pipeline"

print("=== 1. Score against KNOWN for-sale properties ===")
with open(os.path.join(parent, "leads_for_sale.csv")) as f:
    sale = list(csv.DictReader(f))

scores = []
for row in sale:
    reasons_raw = row.get("Reasons", "")
    liens = 0
    has_mortgage = False
    has_assignment = False
    has_affidavit = False
    tax_delinq = False
    oos = False
    tax_bal = 0.0

    m = re.search(r"(\d+)\s*Active\s*Liens?", reasons_raw, re.I)
    if m: liens = int(m.group(1))
    if re.search(r"Has Mortgage|Mortgage Recorded", reasons_raw, re.I): has_mortgage = True
    if re.search(r"Assignment of Rents", reasons_raw, re.I): has_assignment = True
    if re.search(r"Affidavit of Death", reasons_raw, re.I): has_affidavit = True
    if re.search(r"Late Tax|Tax Delinquent|taxes late|tax delinquency", reasons_raw, re.I): tax_delinq = True
    if re.search(r"Out.of.state", reasons_raw, re.I): oos = True

    score, reasons = score_lead(liens=liens, has_mortgage=has_mortgage,
                                has_assignment_rents=has_assignment,
                                has_affidavit_death=has_affidavit,
                                tax_delinquent=tax_delinq, out_of_state=oos)
    scores.append(score)

print(f"For-sale properties scored:")
print(f"  range: {min(scores)} - {max(scores)}")
print(f"  avg: {sum(scores)/len(scores):.0f}")
for b in [(0,30),(30,50),(50,70),(70,85),(85,101)]:
    cnt = sum(1 for s in scores if b[0] <= s < b[1])
    print(f"  {b[0]}-{b[1]:<3}: {cnt} ({cnt/len(scores)*100:.0f}%)")

print()

print("=== 2. Score against full lead set ===")
with open(os.path.join(parent, "all_seller_intent.csv")) as f:
    all_intent = list(csv.DictReader(f))

real = [r for r in all_intent if r.get("apn") != "001-001-001"]
new_scores = []
old_scores = []
for row in real:
    reasons_raw = row.get("Reasons", "")
    liens = 0
    has_mortgage = False
    has_assignment = False
    has_affidavit = False
    tax_delinq = False
    oos = False

    m = re.search(r"(\d+)\s*Active\s*Liens?", reasons_raw, re.I)
    if m: liens = int(m.group(1))
    if re.search(r"Has Mortgage|Mortgage Recorded", reasons_raw, re.I): has_mortgage = True
    if re.search(r"Assignment of Rents", reasons_raw, re.I): has_assignment = True
    if re.search(r"Affidavit of Death", reasons_raw, re.I): has_affidavit = True
    if re.search(r"Late Tax|Tax Delinquent|taxes late|tax delinquency", reasons_raw, re.I): tax_delinq = True
    if re.search(r"Out.of.state", reasons_raw, re.I): oos = True

    score, reasons = score_lead(liens=liens, has_mortgage=has_mortgage,
                                has_assignment_rents=has_assignment,
                                has_affidavit_death=has_affidavit,
                                tax_delinquent=tax_delinq, out_of_state=oos)
    new_scores.append(score)
    try:
        old_scores.append(float(row.get("SellerIntentScore", 0)))
    except:
        old_scores.append(0)

print(f"New scorer (0-100):")
print(f"  range: {min(new_scores)} - {max(new_scores)}")
print(f"  avg: {sum(new_scores)/len(new_scores):.0f}")
for b in [(0,30),(30,50),(50,70),(70,85),(85,101)]:
    cnt = sum(1 for s in new_scores if b[0] <= s < b[1])
    print(f"  {b[0]}-{b[1]:<3}: {cnt} ({cnt/len(new_scores)*100:.0f}%)")

print()
print(f"Old scorer (0-20):")
print(f"  range: {min(old_scores):.1f} - {max(old_scores):.1f}")
print(f"  avg: {sum(old_scores)/len(old_scores):.1f}")

# Show a few top-scoring leads
print()
print("=== 3. Top 5 by new score ===")
combined = list(zip(new_scores, real))
combined.sort(key=lambda x: -x[0])
for score, row in combined[:5]:
    print(f"  Score {score:3d} | {row.get('apn',''):15s} | {row.get('Reasons','')[:80]}")

print()
print("=== 4. Sample score breakdowns ===")
for score, row in combined[:3]:
    _, reasons = score_lead(
        liens=int(re.search(r"(\d+)\s*Active\s*Liens?", row.get("Reasons",""), re.I).group(1)) if re.search(r"(\d+)\s*Active\s*Liens?", row.get("Reasons",""), re.I) else 0,
        has_mortgage=bool(re.search(r"Has Mortgage|Mortgage Recorded", row.get("Reasons",""), re.I)),
        has_assignment_rents=bool(re.search(r"Assignment of Rents", row.get("Reasons",""), re.I)),
        has_affidavit_death=bool(re.search(r"Affidavit of Death", row.get("Reasons",""), re.I)),
        tax_delinquent=bool(re.search(r"Late Tax|Tax Delinquent|taxes late|tax delinquency", row.get("Reasons",""), re.I)),
        out_of_state=bool(re.search(r"Out.of.state", row.get("Reasons",""), re.I)),
    )
    print(f"  {row.get('apn','')} -> Score {score}")
    for r in reasons:
        print(f"    + {r}")
    print()
