"""
Seller Intent Scorer
Predicts likelihood a property owner is motivated to sell, based on
verified distress signals weighted against actual market data.
Range: 0-100. Higher = stronger intent signal.
"""

"""
Market reference weights (derived from 49 actual for-sale properties):
  Assignment of Rents:   present in 88% of for-sale props -> 28 pts
  Tax Delinquency:       present in 84%                  -> 25 pts
  Mortgage Recorded:     present in 73%                  -> 20 pts
  Active Liens:          avg 4.8 on for-sale props       -> 3 pts per lien (cap 24)
  Affidavit of Death:    rare (6%) but high signal       -> 15 pts
  Out-of-State Owner:    absentee indicator              -> 12 pts
  High Tax Balance:      >$1000 amplifies delinquency    -> 8 pts
"""

MAX_SCORE = 100

def score_lead(apn="", liens=0, has_mortgage=False, has_assignment_rents=False,
               has_affidavit_death=False, tax_delinquent=False, tax_balance=0.0,
               out_of_state=False):
    reasons = []
    total = 0

    # 1. Assignment of Rents (strongest signal: 88% of for-sale)
    if has_assignment_rents:
        total += 28
        reasons.append("Assignment of Rents")

    # 2. Tax Delinquency (84% of for-sale)
    if tax_delinquent:
        total += 25
        reasons.append("Tax Delinquency")
        # Amplify if high balance
        if tax_balance >= 1000:
            total += 8
            reasons.append(f"High Tax Balance (${tax_balance:.2f})")

    # 3. Mortgage Recorded (73% of for-sale)
    if has_mortgage:
        total += 20
        reasons.append("Mortgage Recorded")

    # 4. Active Liens (avg 4.8 on for-sale, 3 pts each)
    if liens > 0:
        lien_pts = min(liens * 3, 24)
        total += lien_pts
        reasons.append(f"{liens} Active Lien{'s' if liens > 1 else ''}")

    # 5. Affidavit of Death (rare but high signal)
    if has_affidavit_death:
        total += 15
        reasons.append("Affidavit of Death")

    # 6. Out-of-State Owner (absentee indicator)
    if out_of_state:
        total += 12
        reasons.append("Out-of-State Owner")

    # Cap at 100
    total = min(total, MAX_SCORE)

    return total, reasons


def score_from_dict(row):
    """Score from a dictionary row (CSV or similar)."""
    try:
        liens = int(row.get("active_liens", row.get("liens", 0)))
    except:
        liens = 0

    has_mortgage = row.get("has_mortgage", row.get("mortgages", "False")).lower() in ("true", "1", "yes")
    has_assignment_rents = row.get("has_assignment_of_rents", "False").lower() in ("true", "1", "yes")
    has_affidavit_death = row.get("has_affidavit_of_death", "False").lower() in ("true", "1", "yes")

    tax_delinquent = row.get("v_delinquent", row.get("tax_delinquent", "False")).lower() in ("true", "1", "yes", "late")
    # Also check for tax delinquency in Reasons field
    if not tax_delinquent:
        reasons_field = row.get("Reasons", row.get("reasons", ""))
        tax_delinquent = any(w in reasons_field.lower() for w in ["late", "delinquent", "tax"])

    try:
        raw = row.get("v_total_balance", row.get("tax_balance", "0")).replace("$", "").replace(",", "").strip()
        tax_balance = float(raw) if raw else 0.0
    except:
        tax_balance = 0.0

    out_of_state = row.get("ownership_status", "").lower() == "out_of_state"

    return score_lead(
        apn=row.get("apn", ""),
        liens=liens,
        has_mortgage=has_mortgage,
        has_assignment_rents=has_assignment_rents,
        has_affidavit_death=has_affidavit_death,
        tax_delinquent=tax_delinquent,
        tax_balance=tax_balance,
        out_of_state=out_of_state,
    )
