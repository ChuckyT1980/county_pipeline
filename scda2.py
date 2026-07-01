import re
from typing import List
from itertools import combinations
from alignment import EntityMarkers, AlignmentFeatures, AlignmentResult

def extract_markers(text: str) -> EntityMarkers:
    text = text.upper()
    
    # Trust indicators
    trust = bool(re.search(r'\b(TRUST|TR|REV TR|REVOCABLE TRUST|FAMILY TRUST|LIVING TRUST|UDT|TTEE|CO-TRUSTEE)\b', text))
    # Estate indicators
    estate = bool(re.search(r'\b(EST|ESTATE|EST OF)\b', text))
    # Deceased indicators
    deceased = bool(re.search(r'\b(DECD|DEC\'D|DECEASED)\b', text))
    # LLC indicators
    llc = bool(re.search(r'\b(LLC|L\.L\.C\.)\b', text))
    # Corp indicators
    corp = bool(re.search(r'\b(INC|CORP|CORPORATION|LTD)\b', text))
    
    return EntityMarkers(
        trust=trust,
        estate=estate,
        deceased=deceased,
        llc=llc,
        corporation=corp
    )

def extract_tokens(text: str):
    # Remove markers to isolate names
    text = text.upper()
    markers = [
        r'\bTRUST\b', r'\bTR\b', r'\bREV TR\b', r'\bREVOCABLE TRUST\b', r'\bFAMILY TRUST\b', r'\bLIVING TRUST\b',
        r'\bUDT\b', r'\bTTEE\b', r'\bCO-TRUSTEE\b', r'\bEST\b', r'\bESTATE\b', r'\bEST OF\b',
        r'\bDECD\b', r'\bDEC\'D\b', r'\bDECEASED\b', r'\bLLC\b', r'\bINC\b', r'\bCORP\b', r'\bCORPORATION\b', r'\bLTD\b',
        r'\bOF\b', r'\bTHE\b'
    ]
    for m in markers:
        text = re.sub(m, '', text)
    
    # Extract alpha tokens
    tokens = [t for t in re.findall(r'[A-Z]+', text) if len(t) > 1]
    return tokens

def compute_pairwise_features(s1: str, s2: str) -> AlignmentFeatures:
    m1 = extract_markers(s1)
    m2 = extract_markers(s2)
    
    t1 = extract_tokens(s1)
    t2 = extract_tokens(s2)
    
    set1 = set(t1)
    set2 = set(t2)
    
    exact = s1.upper().strip() == s2.upper().strip()
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    overlap = len(intersection) / len(union) if union else 0.0
    
    # We heuristically assume the last token of the longest string is the surname if no markers are present, 
    # but a safer bet is simply checking if the last tokens match, or if any common token exists.
    # To properly handle "JOHN SMITH" and "SMITH JOHN", we just check if they share tokens.
    # But let's identify "surname overlap" as sharing at least one token >= 3 chars.
    surname_overlap = any(len(t) >= 3 for t in intersection)
    
    # First name overlap could be sharing another token.
    first_name_overlap = len(intersection) >= 2
    
    return AlignmentFeatures(
        exact_match=exact,
        token_overlap=overlap,
        surname_overlap=surname_overlap,
        first_name_overlap=first_name_overlap,
        trust_indicator_diff=m1.trust != m2.trust,
        estate_indicator_diff=m1.estate != m2.estate,
        deceased_indicator_diff=m1.deceased != m2.deceased,
        entity_indicator_diff=(m1.llc != m2.llc) or (m1.corporation != m2.corporation)
    )

def evaluate_pair(s1: str, s2: str) -> AlignmentResult:
    if not s1 or not s2:
        return AlignmentResult("INSUFFICIENT_DATA", 1.0, [s1, s2], ["Missing data"])
        
    f = compute_pairwise_features(s1, s2)
    expl = []
    
    # Base validations
    if f.exact_match:
        return AlignmentResult("EXACT_MATCH", 1.0, [s1, s2], ["Exact string match"])
        
    # Check sparse evidence
    if len(extract_tokens(s1)) < 2 or len(extract_tokens(s2)) < 2:
        # One string is just "JOHN"
        # If it's heavily contained, it's sparse.
        return AlignmentResult("INSUFFICIENT_DATA", 0.5, [s1, s2], ["Sparse name evidence"])

    if f.token_overlap == 1.0 and not f.trust_indicator_diff and not f.estate_indicator_diff and not f.entity_indicator_diff and not f.deceased_indicator_diff:
        # Same words, different order (e.g. SMITH JOHN vs JOHN SMITH)
        expl.append("Token permutation exact match")
        return AlignmentResult("LIKELY_MATCH", 0.9, [s1, s2], expl)
        
    if f.surname_overlap:
        expl.append("Shared surname/core token")
        
        if f.first_name_overlap:
            expl.append("Shared secondary token")
            
        # Check marker drift
        marker_diffs = []
        if f.trust_indicator_diff: marker_diffs.append("Trust indicator diff")
        if f.estate_indicator_diff: marker_diffs.append("Estate indicator diff")
        if f.deceased_indicator_diff: marker_diffs.append("Deceased indicator diff")
        if f.entity_indicator_diff: marker_diffs.append("Entity indicator diff")
        
        if marker_diffs:
            expl.extend(marker_diffs)
            
            # If trust differs but it's the SAME family (JOHN SMITH vs SMITH FAMILY TRUST)
            if f.trust_indicator_diff:
                if f.first_name_overlap or f.token_overlap >= 0.5:
                    # SMITH TRUST vs SMITH FAMILY TRUST
                    return AlignmentResult("PARTIAL_CONFLICT", 0.6, [s1, s2], expl)
                else:
                    # JOHN SMITH vs SMITH FAMILY TRUST
                    expl.append("Individual vs Trust Entity")
                    return AlignmentResult("RELATED_ENTITY", 0.7, [s1, s2], expl)
                    
            if f.estate_indicator_diff or f.deceased_indicator_diff:
                # JOHN SMITH vs EST OF JOHN SMITH
                expl.append("Estate/Deceased drift on same core entity")
                return AlignmentResult("LIKELY_MATCH", 0.85, [s1, s2], expl)
                
            if f.entity_indicator_diff:
                expl.append("Individual vs Corporate Entity")
                return AlignmentResult("RELATED_ENTITY", 0.7, [s1, s2], expl)
                
        else:
            # Shared surname but differing first names (e.g. JOHN SMITH vs ROBERT WILLIAMS? No, they don't share surname. JOHN SMITH vs JANE SMITH)
            if f.first_name_overlap:
                expl.append("High token overlap with minor string difference")
                return AlignmentResult("LIKELY_MATCH", 0.85, [s1, s2], expl)
            else:
                expl.append("Different secondary tokens (potential distinct individuals)")
                return AlignmentResult("PARTIAL_CONFLICT", 0.6, [s1, s2], expl)
                
    else:
        # No surname overlap
        expl.append("No core token overlap")
        return AlignmentResult("CONFLICTED", 0.8, [s1, s2], expl)
        
    # Fallback
    return AlignmentResult("PARTIAL_CONFLICT", 0.5, [s1, s2], ["Ambiguous structural difference"])

def align_candidates(candidates: List[str]) -> AlignmentResult:
    """Evaluates multiple candidates and returns the aggregate alignment."""
    if not candidates:
        return AlignmentResult("INSUFFICIENT_DATA", 1.0, [], ["No candidates"])
    
    unique = list(set(c.strip() for c in candidates if c and c.strip()))
    
    if len(unique) == 0:
        return AlignmentResult("INSUFFICIENT_DATA", 1.0, candidates, ["Null candidates"])
        
    if len(unique) == 1:
        return AlignmentResult("EXACT_MATCH", 1.0, candidates, ["Single unique candidate"])
        
    # Pairwise evaluate
    pairs = list(combinations(unique, 2))
    results = [evaluate_pair(p[0], p[1]) for p in pairs]
    
    # State hierarchy (worst state wins)
    hierarchy = {"CONFLICTED": 5, "PARTIAL_CONFLICT": 4, "RELATED_ENTITY": 3, "INSUFFICIENT_DATA": 2, "LIKELY_MATCH": 1, "EXACT_MATCH": 0}
    
    worst_result = max(results, key=lambda r: hierarchy[r.state])
    
    # Combine explanations
    all_expl = []
    for r in results:
        for e in r.explanation:
            if e not in all_expl:
                all_expl.append(e)
                
    return AlignmentResult(
        state=worst_result.state,
        confidence=worst_result.confidence,
        candidates=candidates, # return original un-deduped for transparency
        explanation=all_expl
    )
