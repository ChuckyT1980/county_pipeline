import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import re
import time
import random
import pandas as pd
from playwright.sync_api import sync_playwright
from tax_pipeline.stage8_skip_trace import clean_name, search_phone

# Butte assessor/recorder data comes in "LAST FIRST [MIDDLE|TITLE]" order without a comma.
# stage8_skip_trace.clean_name() assumes FIRST LAST when no comma is present, which
# produces backwards searches ("MACIAS THOMAS C" -> first="MACIAS", last="C").
# We pre-process the raw name into "LAST, FIRST" form so clean_name parses correctly.
ROLE_SUFFIXES = re.compile(r"\s+(TRUSTEE|TR|EXECUTOR|EXECUTRIX|ADMINISTRATOR|JR|SR|II|III|IV|ETAL|ET AL|CO-TRUSTEE|SUCCESSOR TRUSTEE)$", re.IGNORECASE)
ENTITY_TOKENS = {"LLC", "INC", "CORP", "CORPORATION", "COMPANY", "TRUST", "ESTATE", "HOLDINGS", "PROPERTIES", "ASSOCIATION", "REVOCABLE", "FAMILY", "LP", "PARTNERSHIP"}


def to_last_first(raw: str) -> str:
    """Convert 'LAST FIRST MIDDLE' -> 'LAST, FIRST' so clean_name() parses right.
    Preserves entity names as-is so clean_name can detect and skip them."""
    if not raw or pd.isna(raw):
        return raw
    name = str(raw).strip().upper()
    # If it's an entity, leave it alone so clean_name detects and returns None.
    if any(tok in ENTITY_TOKENS for tok in name.split()):
        return name
    prev = None
    while name != prev:
        prev = name
        name = ROLE_SUFFIXES.sub("", name).strip()
    tokens = name.split()
    if len(tokens) < 2:
        return name
    last = tokens[0]
    first = tokens[1]  # middle initials/names dropped — better hit rate on people-search
    return f"{last}, {first}"

def main():
    call_sheet_file = "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
    print(f"Starting skip trace on {call_sheet_file}...")
    
    df = pd.read_csv(call_sheet_file, dtype=str)
    
    # We will only skip trace the top priority ones or those with missing phone numbers
    todo_idx = df.index[df['phone_number'].isna() | (df['phone_number'] == '')].tolist()
    
    found = 0
    skipped = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        
        for idx in todo_idx:
            raw_name = str(df.at[idx, 'verified_current_owner_name'])
            reordered = to_last_first(raw_name)
            parsed = clean_name(reordered)
            
            if parsed is None:
                skipped += 1
                df.at[idx, 'notes'] = "Entity/Unparsed, skipped phone lookup"
                continue
                
            first, last = parsed
            print(f"[{idx}] {last}, {first} ...", end=" ", flush=True)
            
            result = search_phone(page, first, last, state="CA")
            
            if result["best_phone"]:
                df.at[idx, 'phone_number'] = result["best_phone"]
                print(f"OK: {result['best_phone']}")
                found += 1
            else:
                print("Not found")
                
            df.to_csv(call_sheet_file, index=False)
            time.sleep(random.uniform(2.0, 4.0))
            
        browser.close()
        
    print(f"Done. {found} found, {skipped} skipped.")

if __name__ == '__main__':
    main()
