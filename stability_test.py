import re

raw_text = """================================================================================
SHASTA COUNTY TAX COLLECTOR - NOTICE OF IMPENDING POWER TO SELL
================================================================================
057-120-045-000. HENDERSON, MICHAEL & SARAH. $3,450.00. 123 REDDING BLVD.
054-090-012-000. WILLIAMS, ROBERT DECD EST OF. $12,904.50. 456 COTTONWOOD ST.
112-050-088-000. THE SMITH FAMILY REVOC TR. $5,500.25. 789 ANDERSON WAY.
068-110-004-000. JENKINS, ALICE DECD. $1,200.00. 321 SHASTA LAKE RD.
062340008000. FILIPPELLO, DORIS DECD. $1,801.90. 16740 HILL CREST RD.
"""

APN_STRICT = re.compile(r"(\d{3}-\d{3}-\d{3}-\d{3})")
APN_LOOSE = re.compile(r"(\d{3}[- ]?\d{3}[- ]?\d{3}[- ]?\d{0,4})")

def extract_tier1(text, apn_pattern):
    tier1_apns = set()
    for line in text.split('\n'):
        if not line.strip(): continue
        apn_match = apn_pattern.search(line)
        if apn_match:
            upper = line.upper()
            if "DECEASED" in upper or "ESTATE" in upper or "DECD" in upper or "EST OF" in upper:
                # Normalize the APN format to compare raw numbers
                clean_apn = apn_match.group(0).replace("-", "").replace(" ", "")
                tier1_apns.add(clean_apn)
    return tier1_apns

def run_test():
    strict_leads = extract_tier1(raw_text, APN_STRICT)
    loose_leads = extract_tier1(raw_text, APN_LOOSE)
    
    overlap = strict_leads.intersection(loose_leads)
    total_unique = strict_leads.union(loose_leads)
    
    if len(total_unique) == 0:
        stability = 0
    else:
        stability = (len(overlap) / len(total_unique)) * 100
        
    print("=== SHASTA STABILITY REPLAY TEST ===")
    print(f"Variation A (Strict Regex): {len(strict_leads)} Tier 1 Leads")
    print(f"Variation B (Loose Regex) : {len(loose_leads)} Tier 1 Leads")
    print(f"Lead Stability Score      : {stability:.1f}%\n")
    
    if stability >= 90:
        print("[✓] System is STABLE. Formatting variance does not corrupt Tier 1 signal. Safe to scale to Tehama.")
    elif stability >= 60:
        print("[!] System is USABLE BUT NOISY. Proceed with caution.")
    else:
        print("[X] System is BRITTLE. Do not scale.")

if __name__ == "__main__":
    run_test()
