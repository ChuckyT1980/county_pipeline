"""
Stage 8 Runner — All 3 Counties (Butte, Shasta, Tehama)
Adds best_phone + skip_trace_source to each county's master leads file.

Butte:  tax_pipeline/butte_MASTER_leads_with_liens.csv  (owner col: assessee_name)
Shasta: shasta/shasta_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv (owner col: verified_current_owner_name)
Tehama: tehama/tehama_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv (owner col: verified_current_owner_name)

Only processes individuals (skips LLCs, TRUSTs, INC, etc.)
Saves after every record. Safe to re-run — skips already-filled phones.
"""

import sys, os, re, time, random
import pandas as pd
from playwright.sync_api import sync_playwright

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
TOLL_FREE = re.compile(r"\(?8(00|44|55|66|77|88)\)?")

ENTITY_MARKERS = {
    "LLC", "INC", "CORP", "TRUST", "TR", "ESTATE", "HOLDINGS",
    "PROPERTIES", "ASSOCIATION", "REVOCABLE", "FAMILY", "CO",
    "SKIP_TRACE_REQUIRED", "UNKNOWN", "NAN", "NONE"
}

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(BASE, '..', '..', '..', '..', 'Downloads', 'county_pipeline'))

COUNTY_CONFIG = {
    'butte': {
        'file': os.path.join(PROJECT, 'tax_pipeline', 'butte_MASTER_leads_with_liens.csv'),
        'owner_col': 'assessee_name',
        'output': os.path.join(PROJECT, 'tax_pipeline', 'butte_MASTER_leads_with_liens.csv'),
    },
    'shasta': {
        'file': os.path.join(PROJECT, 'shasta', 'shasta_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv'),
        'owner_col': 'verified_current_owner_name',
        'output': os.path.join(PROJECT, 'shasta', 'shasta_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv'),
    },
    'tehama': {
        'file': os.path.join(PROJECT, 'tehama', 'tehama_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv'),
        'owner_col': 'verified_current_owner_name',
        'output': os.path.join(PROJECT, 'tehama', 'tehama_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv'),
    },
}


def clean_name(raw: str):
    name = str(raw).strip().upper()
    if not name or name in ENTITY_MARKERS:
        return None
    if any(m in name.split() for m in ENTITY_MARKERS):
        return None
    if "," in name:
        parts = name.split(",", 1)
        last = parts[0].strip().title()
        first = parts[1].strip().split()[0].title() if parts[1].strip() else ""
    else:
        tokens = name.split()
        first = tokens[0].title() if tokens else ""
        last = tokens[-1].title() if len(tokens) > 1 else ""
    return (first, last) if first and last else None


def search_phone(page, first: str, last: str, state: str = "CA") -> dict:
    result = {"best_phone": None, "skip_trace_source": None}
    slug = f"{first.lower()}-{last.lower()}_{state}"
    url = f"https://www.fastpeoplesearch.com/name/{slug}"
    try:
        page.goto(url, timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 2.5))
        content = page.content()
        phones = PHONE_RE.findall(content)
        personal = [p for p in phones if not TOLL_FREE.search(p)]
        if personal:
            result["best_phone"] = personal[0].strip()
            result["skip_trace_source"] = "fastpeoplesearch"
            return result
        # Fallback: TruePeopleSearch
        url2 = f"https://www.truepeoplesearch.com/results?name={first}+{last}&citystatezip={state}"
        page.goto(url2, timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 2.5))
        content2 = page.content()
        phones2 = PHONE_RE.findall(content2)
        personal2 = [p for p in phones2 if not TOLL_FREE.search(p)]
        if personal2:
            result["best_phone"] = personal2[0].strip()
            result["skip_trace_source"] = "truepeoplesearch"
    except Exception as e:
        print(f"    [warn] {e}")
    return result


def run_county(county: str, page):
    cfg = COUNTY_CONFIG[county]
    print(f"\n{'='*55}")
    print(f"  STAGE 8 — {county.upper()}")
    print(f"{'='*55}")

    df = pd.read_csv(cfg['file'], low_memory=False)
    owner_col = cfg['owner_col']
    print(f"  Loaded {len(df):,} rows from {os.path.basename(cfg['file'])}")

    if "best_phone" not in df.columns:
        df["best_phone"] = None
    if "skip_trace_source" not in df.columns:
        df["skip_trace_source"] = None

    # Only process rows with an owner name and no phone yet
    needs_phone = df["best_phone"].isna() | df["best_phone"].astype(str).str.strip().isin(["", "nan", "None"])
    has_owner = df[owner_col].notna() if owner_col in df.columns else pd.Series([False]*len(df))
    todo_idx = df[needs_phone & has_owner].index.tolist()
    print(f"  {len(todo_idx):,} records need phone lookup.")

    found = 0
    skipped = 0

    for i, idx in enumerate(todo_idx, 1):
        raw_name = str(df.at[idx, owner_col])
        parsed = clean_name(raw_name)

        if parsed is None:
            skipped += 1
            df.at[idx, "skip_trace_source"] = "skipped_entity"
            # Save periodically
            if i % 50 == 0:
                df.to_csv(cfg['output'], index=False)
            continue

        first, last = parsed
        print(f"  [{i}/{len(todo_idx)}] {county} | {last}, {first} ...", end=" ", flush=True)

        result = search_phone(page, first, last)

        if result["best_phone"]:
            df.at[idx, "best_phone"] = result["best_phone"]
            df.at[idx, "skip_trace_source"] = result["skip_trace_source"]
            print(f"FOUND: {result['best_phone']}")
            found += 1
        else:
            df.at[idx, "skip_trace_source"] = "not_found"
            print("—")

        # Save after every record so no progress is lost
        df.to_csv(cfg['output'], index=False)
        time.sleep(random.uniform(2.0, 4.0))

    print(f"\n  {county.upper()} DONE: {found} phones found, {skipped} entities skipped, {len(todo_idx)-found-skipped} not found.")
    return found, skipped


def main():
    counties = sys.argv[1:] if len(sys.argv) > 1 else ['butte', 'shasta', 'tehama']
    print(f"Running Stage 8 skip trace for: {', '.join(counties)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        totals = {}
        for county in counties:
            if county not in COUNTY_CONFIG:
                print(f"Unknown county: {county}. Skipping.")
                continue
            found, skipped = run_county(county, page)
            totals[county] = {'found': found, 'skipped': skipped}

        browser.close()

    print(f"\n{'='*55}")
    print("  STAGE 8 COMPLETE — ALL COUNTIES")
    print(f"{'='*55}")
    for county, stats in totals.items():
        print(f"  {county.upper()}: {stats['found']} phones found, {stats['skipped']} entities skipped")


if __name__ == "__main__":
    main()
