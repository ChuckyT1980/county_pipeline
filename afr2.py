import re

def extract_identity_tokens(numeric_tokens):
    """Extracts tokens that structurally look like APNs."""
    id_tokens = set()
    for t in numeric_tokens:
        digits = re.sub(r'[^\d]', '', t)
        if len(digits) >= 9:
            id_tokens.add(digits)
    return id_tokens

def compute_similarity(v1, v2):
    id_tokens_1 = extract_identity_tokens(v1.get("numeric_tokens", []))
    id_tokens_2 = extract_identity_tokens(v2.get("numeric_tokens", []))
    
    # 1. Direct Identity Conflict
    if id_tokens_1 and id_tokens_2:
        overlap = id_tokens_1.intersection(id_tokens_2)
        if not overlap:
            return -1.0 # Cannot-Link
        else:
            return 1.0 # Must-Link (or very high confidence)
            
    # 2. Token Overlap
    ngrams_1 = set(v1.get("alphanumeric_ngrams", []))
    ngrams_2 = set(v2.get("alphanumeric_ngrams", []))
    hashes_1 = set(v1.get("rare_token_hashes", []))
    hashes_2 = set(v2.get("rare_token_hashes", []))
    
    shared_ngrams = ngrams_1.intersection(ngrams_2)
    shared_hashes = hashes_1.intersection(hashes_2)
    
    # Template collision check
    if v1.get("token_shapes") == v2.get("token_shapes") and v1.get("numeric_tokens") != v2.get("numeric_tokens"):
        return -1.0 # Structural identical but different values = different instances of a template
        
    if len(shared_hashes) > 0 or len(shared_ngrams) > 2:
        jaccard = len(shared_ngrams) / max(1, len(ngrams_1.union(ngrams_2)))
        
        # If Jaccard is low, it's just a common owner or common address, NOT enough for identity
        if jaccard < 0.2:
            return 0.1 # Very low confidence, won't cluster
        return 0.6
        
    return 0.0

def resolve_identities(afr1_outputs):
    nodes = {out["page_id"]: out["signal_vector"] for out in afr1_outputs}
    edges = []
    cannot_link = set()
    
    node_ids = list(nodes.keys())
    for i in range(len(node_ids)):
        for j in range(i+1, len(node_ids)):
            id1, id2 = node_ids[i], node_ids[j]
            score = compute_similarity(nodes[id1], nodes[id2])
            
            if score == -1.0:
                cannot_link.add((id1, id2))
                cannot_link.add((id2, id1))
            elif score > 0.4:
                edges.append((id1, id2, score))
                
    edges.sort(key=lambda x: x[2], reverse=True)
    
    parent = {n: n for n in nodes}
    clusters = {n: {n} for n in nodes}
    
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
        
    def can_merge(c1, c2):
        for n1 in clusters[c1]:
            for n2 in clusters[c2]:
                if (n1, n2) in cannot_link:
                    return False
        return True
        
    for id1, id2, score in edges:
        root1 = find(id1)
        root2 = find(id2)
        if root1 != root2:
            if can_merge(root1, root2):
                parent[root2] = root1
                clusters[root1].update(clusters[root2])
                del clusters[root2]
                
    out_clusters = []
    orphans = []
    
    cluster_idx = 1
    for root, members in clusters.items():
        if len(members) == 1:
            orphans.extend(list(members))
        else:
            out_clusters.append({
                "cluster_id": f"C{cluster_idx}",
                "pages": list(members),
                "confidence": 0.85,
                "stability_score": 0.8
            })
            cluster_idx += 1
            
    return {
        "entity_clusters": out_clusters,
        "orphan_pages": orphans,
        "graph_metrics": {
            "avg_degree": round(len(edges) / len(nodes) * 2, 2) if nodes else 0,
            "fragmentation_index": round(len(out_clusters) / len(nodes), 2) if nodes else 0
        }
    }
