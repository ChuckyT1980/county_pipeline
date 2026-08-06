"""Score all Butte leads and generate output."""
import csv, sys
sys.path.insert(0, '.')
from seller_intent_scorer import score_from_dict

with open("butte_MASTER_leads_with_liens.csv") as f:
    rows = list(csv.DictReader(f))

results = []
for r in rows:
    s, reasons = score_from_dict(r)
    results.append({
        "apn": r["asmt"],
        "owner": r.get("owner_name", r.get("assessee_name", "")).strip(),
        "address": r.get("address", ""),
        "score": s,
        "balance": r.get("v_total_balance", "0"),
        "liens": r.get("active_liens", "0"),
        "mortgages": r.get("mortgages", "0"),
        "assignment": r.get("has_assignment_of_rents", "False"),
        "reasons": "; ".join(reasons),
    })

# Buckets
buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
for r in results:
    s = r["score"]
    if s <= 20: buckets["0-20"] += 1
    elif s <= 40: buckets["21-40"] += 1
    elif s <= 60: buckets["41-60"] += 1
    elif s <= 80: buckets["61-80"] += 1
    else: buckets["81-100"] += 1

print("=== BUTTE SELLER INTENT SCORES ===")
print(f"Total leads: {len(results)}")
print(f"Average score: {sum(r['score'] for r in results)/len(results):.1f}")
print()
print("Distribution:")
for k, v in buckets.items():
    bar = "#" * (v * 50 // len(results))
    pct = v * 100 // len(results) if v > 0 else 0
    print(f"  {k:>7}: {v:>4} ({pct:>2}%) {bar}")

print()
print("=== TOP 30 LEADS (score >= 75) ===")
results.sort(key=lambda x: (-x["score"], x["apn"]))
print(f"{'APN':^14} {'SCORE':>5} {'OWNER':^40} {'BALANCE':>10} {'LIENS':>5} {'MTG':>3} {'AOR':>3}")
print("-" * 90)
for r in results:
    if r["score"] < 75:
        continue
    print(f"{r['apn']:>14} {r['score']:>5} {r['owner'][:38]:38s} {r['balance']:>10} {r['liens']:>5} {r['mortgages']:>3} {r['assignment'][:3]:>3}")

# Save top leads
top30 = [r for r in results if r["score"] >= 75]
print(f"\nHigh-priority leads (75+): {len(top30)}")

# Also save CSV
with open("butte_scored_leads.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["apn","owner","address","score","balance","liens","mortgages","assignment","reasons"])
    w.writeheader()
    w.writerows(results)

print(f"\nFull results saved to butte_scored_leads.csv ({len(results)} rows)")
