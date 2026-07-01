APN_PATTERN_CA = r"(\d{3}-\d{3}-\d{3}(?:-\d{3})?)"
APN_PATTERN_GENERIC = r"((?:\d-?){10,12})"

DECEASED_KEYWORDS = ["DECD", "EST OF", "ESTATE", "DEC'D", "DECEASED", "PROBATE", "UNKNOWN"]
TRUST_KEYWORDS = ["TRUST", "TR", "RECOV TR", "FAM TR", "ETAL", "ET AL"]

# Heavy distress vocabulary for the CPS-1 diagnostic hook
DISTRESS_VOCAB = ["TAX-DEFAULTED", "AUCTION", "DELINQUENT", "POWER TO SELL", "DEFAULT"]

TIER_RULES = {
    "TIER_1": DECEASED_KEYWORDS,
    "TIER_2": TRUST_KEYWORDS,
    "TIER_3": []
}
