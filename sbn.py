from bs4 import BeautifulSoup
import re

def normalize_html_to_pairs(html_content):
    """
    SBN-1: Extracts key-value pairs from messy HTML.
    Preserves duplicate keys. Does not infer meaning.
    """
    if not html_content or "<!-- MISSING ENTIRELY -->" in html_content or "<!-- EMPTY PAGE -->" in html_content:
        return []
        
    soup = BeautifulSoup(html_content, 'html.parser')
    pairs = []
    
    # 1. Look for text with colons (inline key-value like "Owner: UNKNOWN")
    for elem in soup.find_all(text=True):
        text = elem.strip()
        if not text: continue
        
        # Check if the text itself contains a colon
        if ":" in text:
            parts = text.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            
            # If value is empty, the next element might be the value
            if not val:
                next_elem = elem.find_next()
                if next_elem and next_elem.text.strip():
                    val = next_elem.text.strip()
            if key and val:
                pairs.append((key, val))
                continue
    
    # 2. Look for adjacent divs or spans with class="field" or "label" and "value"
    for label_elem in soup.find_all(lambda tag: tag.name in ['div', 'span'] and tag.get('class') and any(c in ['field', 'label'] for c in tag.get('class'))):
        key = label_elem.text.strip().replace(":", "").strip()
        
        # Next sibling div/span is usually the value
        next_sibling = label_elem.find_next_sibling(lambda tag: tag.name in ['div', 'span'])
        if next_sibling:
            val = next_sibling.text.strip()
            if key and val:
                # check if already added by inline logic
                if not any(k == key and v == val for k, v in pairs):
                    pairs.append((key, val))
                continue
                
    # 3. Look for table rows
    for row in soup.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 2:
            key = cells[0].text.strip().replace(":", "").strip()
            val = cells[1].text.strip()
            if key and val:
                pairs.append((key, val))
                
    # 4. Look for row divs
    for row in soup.find_all('div', class_='row'):
        spans = row.find_all('span')
        if len(spans) >= 2:
            key = spans[0].text.strip().replace(":", "").strip()
            val = spans[1].text.strip()
            if key and val:
                pairs.append((key, val))
                
    # 5. Fallback sequential divs if they look like alternating key/val (like r2a, r2b)
    # Assessor HTML r2a: <div>Property Location</div><div>321 SHASTA LAKE RD</div>
    # Only if not already captured
    divs = soup.find_all('div', recursive=False)
    if not pairs and len(divs) >= 2:
        for i in range(len(divs) - 1):
            key = divs[i].text.strip().replace(":", "").strip()
            val = divs[i+1].text.strip()
            # simple heuristic: if val looks like a value (not empty) and key is short
            if key and val and len(key) < 30:
                pairs.append((key, val))
                
    return pairs
