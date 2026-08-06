from bs4 import BeautifulSoup
import re
import math

def compute_signal_vector(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    text = soup.get_text(separator=' ', strip=True)
    text_length = len(text)
    if text_length == 0:
        return {
            "label_density": 0.0,
            "table_ratio": 0.0,
            "numeric_density": 0.0,
            "dollar_sign_density": 0.0,
            "keyword_hits": 0,
            "is_empty": True,
            "numeric_tokens": [],
            "token_shapes": [],
            "alphanumeric_ngrams": [],
            "rare_token_hashes": []
        }
        
    divs = len(soup.find_all('div'))
    spans = len(soup.find_all('span'))
    tables = len(soup.find_all('table'))
    trs = len(soup.find_all('tr'))
    
    total_elements = divs + spans + tables + trs + 1
    table_ratio = (tables + trs) / total_elements
    label_density = (divs + spans) / total_elements
    
    digits = len(re.findall(r'\d', text))
    numeric_density = digits / text_length
    
    dollars = len(re.findall(r'\$', text))
    dollar_sign_density = dollars / text_length if text_length > 0 else 0
    
    # We look for structural key keywords but do NOT infer meaning
    # We just count how many structural keys exist
    keywords = ['owner', 'address', 'location', 'due', 'amount', 'delinquent', 'use', 'acreage', 'size']
    keyword_hits = sum(1 for kw in keywords if kw in text.lower())
    
    # Extract Structural Token Signatures
    numeric_tokens = set()
    token_shapes = set()
    alphanumeric_ngrams = set()
    rare_token_hashes = set()
    
    # 1. Numeric tokens and their shapes
    # e.g., "057-120-045-000", "8421.22", "$1,200", "1.25"
    num_matches = re.findall(r'\$?\d+(?:[.,-]\d+)*', text)
    for m in num_matches:
        numeric_tokens.add(m)
        shape = re.sub(r'\d', 'D', m)
        token_shapes.add(shape)
        
    # 2. Alphanumeric N-grams (ignoring structure)
    # Extract purely words and numbers without punctuation
    alpha_num = re.findall(r'[A-Za-z0-9]+', text)
    for t in alpha_num:
        if len(t) > 3: # Ignore short filler words
            alphanumeric_ngrams.add(t.upper())
            
    # 3. Rare token hashes
    # To identify rare combinations like "JOHNSON HOLDINGS LLC"
    import hashlib
    for i in range(len(alpha_num) - 2):
        trigram = "".join(alpha_num[i:i+3]).upper()
        h = hashlib.md5(trigram.encode()).hexdigest()[:8]
        rare_token_hashes.add(h)

    return {
        "label_density": round(label_density, 3),
        "table_ratio": round(table_ratio, 3),
        "numeric_density": round(numeric_density, 3),
        "dollar_sign_density": round(dollar_sign_density, 3),
        "keyword_hits": keyword_hits,
        "is_empty": False,
        "numeric_tokens": list(numeric_tokens),
        "token_shapes": list(token_shapes),
        "alphanumeric_ngrams": list(alphanumeric_ngrams),
        "rare_token_hashes": list(rare_token_hashes)
    }

def classify_page(html_content, page_id):
    vector = compute_signal_vector(html_content)
    
    if vector["is_empty"]:
        struct_type = "EMPTY_PAGE"
        conf = 1.0
    elif vector["dollar_sign_density"] > 0 or vector["numeric_density"] > 0.15:
        # High numeric/financial footprint
        struct_type = "FINANCIAL_SPARSE" if vector["label_density"] < 0.5 else "FINANCIAL_DENSE"
        conf = 0.85
    elif vector["table_ratio"] > 0.2:
        # High table footprint
        struct_type = "TABLE_HEAVY"
        conf = 0.90
    elif vector["label_density"] > 0.6:
        # High div/span label footprint
        struct_type = "LABEL_HEAVY"
        conf = 0.80
    else:
        struct_type = "MIXED"
        conf = 0.50
        
    return {
        "page_id": page_id,
        "structure_type": struct_type,
        "signal_vector": vector,
        "routing_confidence": conf,
        "bundle_hint": "UNASSIGNED"
    }

if __name__ == "__main__":
    import os, json
    in_dir = "data/raw/scrambled_shasta"
    results = []
    
    for f in os.listdir(in_dir):
        if not f.endswith(".html"): continue
        with open(os.path.join(in_dir, f)) as file:
            html = file.read()
        
        result = classify_page(html, f)
        results.append(result)
        
    for r in results:
        print(json.dumps(r, indent=2))
