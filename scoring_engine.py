import json
import csv

def compute_score(lead):
    event = lead["distress_event"]
    snap = lead.get("property_snapshot", {}) or {}

    score = 0
    signals = {}

    # 1. DISTRESS PERSISTENCE
    persistence = 2025 - int(event["default_year"])
    persistence_score = persistence * 12
    score += persistence_score
    signals["persistence"] = persistence

    # 2. FINANCIAL PRESSURE
    amount_due = float(event.get("amount_due", 0))
    financial_score = min(amount_due / 500, 60)
    score += financial_score
    signals["amount_due"] = amount_due

    # 3. EQUITY PROXY
    assessed_total = snap.get("total_assessed_value")
    if assessed_total and assessed_total > 0:
        distress_ratio = amount_due / assessed_total
        score += min(distress_ratio * 100, 40)
        signals["equity_proxy"] = distress_ratio
        if assessed_total < 200000:
            score += 15
    else:
        score += 8
        signals["equity_proxy"] = None

    # 4. ABSENTEE SIGNAL
    situs = snap.get("situs_address")
    mailing = snap.get("mailing_address")
    signals["absentee"] = False
    
    if mailing and situs:
        if mailing.strip().lower() != situs.strip().lower():
            score += 20
            signals["absentee"] = True
    if not situs:
        score += 10
        signals["absentee"] = True # Implicitly absentee if no situs

    # 5. LAND / SIMPLICITY BONUS
    land_use = (snap.get("land_use") or "").lower()
    signals["land_flag"] = False
    if "vacant" in land_use or "land" in land_use:
        score += 12
        signals["land_flag"] = True

    score = round(score, 2)
    
    # Rank Bucket
    if score >= 80:
        bucket = "A+ (Acquisition Priority)"
    elif score >= 50:
        bucket = "A (Strong Lead)"
    elif score >= 30:
        bucket = "B (Watchlist)"
    else:
        bucket = "C (Noise)"

    return {
        "apn": lead["property_core"]["apn_normalized"],
        "county": lead["property_core"]["county"],
        "score": score,
        "signals": signals,
        "rank_bucket": bucket,
        "raw_owner": event.get("raw_owner_signal")
    }

def run_scoring():
    with open("unified_leads_sample.json", "r") as f:
        leads = json.load(f)
        
    scored = [compute_score(lead) for lead in leads]
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    print("[DONE] Scoring Complete.")
    for s in scored[:5]:
        print(f"{s['rank_bucket']} - Score: {s['score']} | APN: {s['apn']}")
        
    with open("scored_leads.json", "w") as f:
        json.dump(scored, f, indent=2)

if __name__ == "__main__":
    run_scoring()
