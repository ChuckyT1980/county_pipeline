import re
from canonical import IntelligenceRecord, Layer2Signals

DECEASED_PATTERNS = ["DECD", "DEC'D", "DECEASED", "EST OF", "ESTATE"]
TRUST_PATTERNS    = ["TRUST", "REVOC TR", "FAM TR", "RECOV TR", "TR"]
ENTITY_PATTERNS   = ["LLC", "INC", "CORP", "CORPORATION", "LTD"]
MULTI_PATTERNS    = ["ETAL", "ET AL", "&", "AND"]

def generate_signals(record: IntelligenceRecord) -> None:
    """Populates Layer 2 Signals based entirely on Layer 1 Facts."""
    facts = record.facts
    signals = record.signals

    # Only trust owner string if we have high agreement
    if facts.owner.state in ["VERIFIED", "HIGH_CONFIDENCE"]:
        owner_str = facts.owner.value.upper()
        
        # Simple regex / string matching for owner patterns
        signals.deceased_owner = any(p in owner_str for p in DECEASED_PATTERNS)
        signals.trust_owner = any(p in owner_str for p in TRUST_PATTERNS)
        signals.entity_owner = any(p in owner_str for p in ENTITY_PATTERNS)
        signals.multiple_owners = any(p in owner_str for p in MULTI_PATTERNS)
    else:
        # If identity is conflicted, we fail-safe by NOT assigning these signals
        signals.deceased_owner = False
        signals.trust_owner = False
        signals.entity_owner = False
        signals.multiple_owners = False

    # Address comparison
    mail_addr = facts.mailing_address.value.upper()
    situs_addr = facts.situs_address.value.upper()

    # Heuristic for owner-occupied: mailing matches situs
    if facts.mailing_address.state in ["VERIFIED", "HIGH_CONFIDENCE"] and facts.situs_address.state in ["VERIFIED", "HIGH_CONFIDENCE"]:
        if mail_addr and situs_addr and len(mail_addr) > 5 and (situs_addr in mail_addr or mail_addr in situs_addr):
            signals.owner_occupied = True
        else:
            signals.owner_occupied = False
    else:
        signals.owner_occupied = False

    # Heuristic for out-of-state
    if facts.mailing_address.state in ["VERIFIED", "HIGH_CONFIDENCE"]:
        if mail_addr and len(mail_addr) > 10 and not re.search(r'\bCA\b', mail_addr):
            signals.out_of_state_owner = True
        else:
            signals.out_of_state_owner = False
    else:
        signals.out_of_state_owner = False
