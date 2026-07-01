def map_pairs_to_layer_1(pairs, source_name):
    """
    SCDA-1: Schema Drift Absorber.
    Maps random county labels to Layer 1 slots without modifying the values.
    Emits a dict of {layer_1_field: raw_value}.
    Handles multiple values by joining or keeping list, but contract asks for raw string.
    If multiple, we can join with " | ".
    """
    mapping = {
        "owner_raw": ["owner name", "owner", "registered owner"],
        "situs_address": ["situs address", "situs location", "property location"],
        "amount_due": ["taxes due", "delinquent amount", "amount due"],
        "land_use": ["land use code", "use", "land use"],
        "acreage": ["acreage", "size (acres)"]
    }
    
    extracted = {}
    
    for key, val in pairs:
        key_lower = key.lower()
        
        # Find which Layer 1 field this maps to
        target_field = None
        for l1_field, variants in mapping.items():
            if key_lower in variants:
                target_field = l1_field
                break
                
        if target_field:
            if target_field in extracted:
                # Deliberate conflict preservation!
                extracted[target_field] = extracted[target_field] + " | " + val
            else:
                extracted[target_field] = val
                
    return extracted
