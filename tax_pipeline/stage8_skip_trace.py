"""
Stage 8: Free Skip Trace — best-effort phone number lookup via Playwright.
Uses FastPeopleSearch.com (free, no login).
Adds 'best_phone' and 'skip_trace_source' columns to the MASTER leads file.

Usage:
    python -m tax_pipeline.stage8_skip_trace tehama
"""
import sys
import os
import re
import time
import random
import pandas as pd
from playwright.sync_api import sync_playwright

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")


def clean_name(raw: str):
    """
    Parse 'LAST, FIRST MIDDLE' or 'FIRST LAST' into (first, last).
    Returns None for business entities.
    """
    name = str(raw).strip().upper()
    if not name or name in {"NAN", "NONE", "UNKNOWN"}:
        return None

    entity_markers = {"LLC", "INC", "CORP", "TRUST", "TR", "ESTATE", "HOLDINGS",
                      "PROPERTIES", "ASSOCIATION", "REVOCABLE", "FAMILY", "CO"}
    if any(m in name.split() for m in entity_markers):
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
    """
    Search FastPeopleSearch via Playwright. Returns first phone found or None.
    """
    result = {"best_phone": None, "skip_trace_source": None}

    slug = f"{first.lower()}-{last.lower()}_{state}"
    url = f"https://www.fastpeoplesearch.com/name/{slug}"

    try:
        page.goto(url, timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 2.5))

        content = page.content()
        phones = PHONE_RE.findall(content)

        # Filter out obvious non-personal numbers (800, 888, 877, etc.)
        toll_free = re.compile(r"\(?8(00|44|55|66|77|88)\)?")
        personal = [p for p in phones if not toll_free.search(p)]

        if personal:
            result["best_phone"] = personal[0].strip()
            result["skip_trace_source"] = "fastpeoplesearch"
            return result

        # Try TruePeopleSearch as fallback
        url2 = f"https://www.truepeoplesearch.com/results?name={first}+{last}&citystatezip={state}"
        page.goto(url2, timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 2.5))

        content2 = page.content()
        phones2 = PHONE_RE.findall(content2)
        personal2 = [p for p in phones2 if not toll_free.search(p)]
        if personal2:
            result["best_phone"] = personal2[0].strip()
            result["skip_trace_source"] = "truepeoplesearch"

    except Exception:
        pass

    return result


def run_skip_trace(county: str):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    master_file = os.path.join(base_dir, f"{county}_MASTER_leads_with_liens.csv")

    if not os.path.exists(master_file):
        print(f"Error: {master_file} not found.")
        sys.exit(1)

    df = pd.read_csv(master_file)
    print(f"[Stage 8] Skip Trace for {county.upper()} — {len(df)} leads")

    if "best_phone" not in df.columns:
        df["best_phone"] = None
    if "skip_trace_source" not in df.columns:
        df["skip_trace_source"] = None

    owner_col = (
        "assessee_name" if "assessee_name" in df.columns
        else "owner_name" if "owner_name" in df.columns
        else None
    )
    if owner_col is None:
        print("  No owner name column found. Run stage7 first.")
        sys.exit(1)

    needs_phone = df["best_phone"].isna() | (
        df["best_phone"].astype(str).str.strip().isin(["", "nan", "None"])
    )
    todo_idx = df[needs_phone].index.tolist()
    print(f"  {len(todo_idx)} leads need phone lookup.")

    found = 0
    skipped_entity = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for idx in todo_idx:
            raw_name = str(df.at[idx, owner_col])
            parsed = clean_name(raw_name)

            if parsed is None:
                skipped_entity += 1
                df.at[idx, "skip_trace_source"] = "skipped_entity"
                continue

            first, last = parsed
            print(f"  [{idx}] {last}, {first} ...", end=" ", flush=True)

            result = search_phone(page, first, last, state="CA")

            if result["best_phone"]:
                df.at[idx, "best_phone"] = result["best_phone"]
                df.at[idx, "skip_trace_source"] = result["skip_trace_source"]
                print(f"✓ {result['best_phone']}")
                found += 1
            else:
                df.at[idx, "skip_trace_source"] = "not_found"
                print("—")

            # Save after every lead so progress isn't lost
            df.to_csv(master_file, index=False)
            time.sleep(random.uniform(2.0, 4.0))

        browser.close()

    print(f"\n[Stage 8] Done. {found}/{len(todo_idx)} phones found "
          f"({skipped_entity} entities skipped).")
    print(f"  Saved → {master_file}")


if __name__ == "__main__":
    county_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "tehama"
    run_skip_trace(county_arg)
