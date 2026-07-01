def validate_layer_1(record):
    """
    Validates the purity and completeness of a Layer 1 extraction.
    Returns: status (ACCEPT, QUARANTINE, REJECT)
    """
    has_owner = bool(record.get("owner_raw"))
    has_address = bool(record.get("situs_address")) or bool(record.get("mailing_address"))
    has_tax = record.get("amount_due") is not None
    
    # REJECT condition: Almost complete nulls (Record 5)
    if not has_owner and not has_address and not has_tax:
        return "REJECT"
    if record.get("owner_raw") == "UNKNOWN" and record.get("amount_due") is None:
        return "REJECT"
        
    # QUARANTINE condition: Missing major block (e.g. tax block in Record 3)
    if not has_tax:
        return "QUARANTINE"
        
    # QUARANTINE condition: Malformed structural data (e.g. Acreage in Record 4)
    acreage_raw = record.get("acreage_raw", "")
    if isinstance(acreage_raw, str) and ("acres" in acreage_raw.lower() or "," in acreage_raw):
        # We know it's messy, but we didn't crash. We flag it.
        return "QUARANTINE"
        
    # QUARANTINE condition: Conflicting owners (Record 1, 4)
    # The owner_raw string will have "|" if SCDA-1 merged them
    if " | " in (record.get("owner_raw") or ""):
        return "QUARANTINE"
        
    # Default ACCEPT
    return "ACCEPT"

if __name__ == "__main__":
    import json
    with open("data/raw/shasta_live.jsonl") as f:
        records = [json.loads(line) for line in f]
        
    print(f"{'APN':<20} | {'STATUS':<15}")
    print("-" * 40)
    for r in records:
        status = validate_layer_1(r)
        print(f"{r['apn']:<20} | {status:<15}")
