#!/usr/bin/env python3
"""
Recorder enrichment with county-specific config support.
Usage: python -m tax_pipeline.stage7_recorder_enrich <county>
"""
import pandas as pd
import time
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import sys
import os
import re

try:
    from tax_pipeline.recorder_config import RECORDER_CONFIG
    from tax_pipeline.config import COUNTY_CONFIG
except ImportError:
    from recorder_config import RECORDER_CONFIG
    from config import COUNTY_CONFIG

# Document classification lists (unchanged)
LIEN_TYPES = [
    "FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT", "LIS PENDENS"
]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST", "ASSIGNMENT OF DEED OF TRUST", "ASSIGNMENT OF RENTS"]

def format_name(name):
    """Parse an owner name string into {lastName, firstName} for EagleWeb search."""
    name = str(name).strip().upper()
    if not name or name in {"NAN", "NONE", "UNKNOWN", "UNKNOWN OWNER"}:
        return None

    markers = ["LLC", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "TRUST", "TR", "REVOC", "ESTATE",
               "HOLDINGS", "PROPERTIES", "SERVICES", "ASSOCIATION", "REVOCABLE", "FAMILY"]
    is_entity = any(m in name.upper().split() for m in markers)

    if is_entity:
        return {"lastName": name.replace(",", " ").strip(), "firstName": ""}

    if name.count(",") == 1:
        parts = [p.strip() for p in name.split(",")]
        last = parts[0]
        first = parts[1].split()[0] if parts[1].split() else ""
        return {"lastName": last, "firstName": first}

    tokens = name.replace(",", " ").split()
    if len(tokens) >= 2:
        return {"lastName": tokens[0], "firstName": tokens[1]}
    return {"lastName": name, "firstName": ""}


def ensure_search_ready(page, cfg, state_file):
    """Handle EagleWeb wall states and return True when search page is ready."""
    print("CFG IN ENSURE:", cfg)
    for attempt in range(3):
        print(f"ATTEMPT {attempt}")
        try:
            # Keepalive modal
            for txt in cfg.get("keepalive_text", []):
                keepalive = page.locator(f"button:has-text('{txt}')")
                if keepalive.count() > 0 and keepalive.first.is_visible(timeout=1500):
                    keepalive.first.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(1)
                    continue

            # Disclaimer wall
            sel = cfg.get("disclaimer_selector")
            if sel:
                disclaimer = page.locator(sel)
                # Also do a URL-based check — Tyler SPA may redirect to a disclaimer URL
                on_disclaimer_page = cfg.get("disclaimer_url_fragment", "") in page.url.lower()
                visible = False
                try:
                    visible = disclaimer.count() > 0 and disclaimer.first.is_visible(timeout=5000)
                except Exception:
                    pass
                if visible or on_disclaimer_page:
                    start = time.time()
                    accepted = False
                    while time.time() - start < 45:
                        try:
                            disabled = page.eval_on_selector(sel, 'btn => btn.disabled')
                            if not disabled:
                                page.click(sel)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    pass
                                try:
                                    page.context.storage_state(path=state_file)
                                except Exception:
                                    pass
                                accepted = True
                                break
                        except Exception:
                            pass
                        time.sleep(0.5)
                    if not accepted:
                        page.evaluate(f"""
                            const btn = document.querySelector('{sel}');
                            if (btn) {{ btn.disabled = false; btn.click(); }}
                        """)
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                        time.sleep(1)
                    if cfg.get("post_disclaimer_navigate"):
                        return True
                    continue

            # Search field visible?
            sf = page.locator(cfg["search_field"])
            if sf.count() > 0 and sf.is_visible(timeout=3000):
                return True

            if cfg.get("post_disclaimer_navigate"):
                return True

            time.sleep(2)

        except Exception as e:
            print(f"  [ensure_search_ready] attempt {attempt+1} error: {e}")
            time.sleep(2)

    print("  [ensure_search_ready] FAILED — page did not reach search state. RETURNING FALSE")
    return False


def login_if_needed(page, cfg, state_file):
    """Handle guest login for counties that require it."""
    if not cfg.get("needs_guest_login"):
        return True
    try:
        print("  [LOGIN] Guest login required; submitting form...")
        page.wait_for_load_state("networkidle", timeout=30000)
        # Common EagleWeb guest login: form submits automatically, but if not:
        if page.url.lower().startswith("https://eagleweb.co.lassen.ca.us/eweb/web/login"):
            submit = page.locator("input[type='submit']")
            if submit.count() > 0 and submit.first.is_visible(timeout=3000):
                submit.first.click()
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(1)
        page.context.storage_state(path=state_file)
        return True
    except Exception as e:
        print(f"  [LOGIN] Error: {e}")
        return False


def scrape_liens(county="tehama"):
    if county not in RECORDER_CONFIG:
        print(f"Error: no recorder config for county '{county}'.")
        print(f"Supported: {', '.join(RECORDER_CONFIG.keys())}")
        sys.exit(1)

    cfg = RECORDER_CONFIG[county]
    print(f"[Stage 7] Starting Recorder Enrichment for {county.upper()} via Playwright...")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, f"{county}_MASTER_leads_with_liens.csv")
    output_file = os.path.join(base_dir, f"{county}_MASTER_leads_with_liens.csv")

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        sys.exit(1)

    df = pd.read_csv(input_file)

    for col in ["active_liens", "mortgages"]:
        if col not in df.columns:
            df[col] = 0
    for col in ["has_assignment_of_rents", "has_affidavit_of_death"]:
        if col not in df.columns:
            df[col] = False
    # Ensure ownership_status is string type (not float64 from NaN rows)
    if "ownership_status" not in df.columns:
        df["ownership_status"] = "Current"
    df["ownership_status"] = df["ownership_status"].fillna("Current").astype(str)

    # ── Sync owner_name into assessee_name if the latter is empty ──
    if "owner_name" in df.columns and "assessee_name" in df.columns:
        df["assessee_name"] = df["assessee_name"].astype(object).fillna("")
        empty_mask = df["assessee_name"].astype(str).str.strip().isin(["", "nan", "NAN", "None"])
        df.loc[empty_mask, "assessee_name"] = df.loc[empty_mask, "owner_name"]
    owner_col = "assessee_name" if "assessee_name" in df.columns else "owner_name" if "owner_name" in df.columns else None
    needs_backfill = (
        owner_col is None
        or df[owner_col].isna().any()
        or (df[owner_col].astype(str).str.strip() == "").any()
        or (df[owner_col].astype(str).str.upper() == "NAN").any()
    )

    if needs_backfill and county in COUNTY_CONFIG:
        tax_cfg = COUNTY_CONFIG[county]
        if owner_col is None:
            df["assessee_name"] = None
            owner_col = "assessee_name"

        asmt_col = next((c for c in ["asmt", "apn", "fee_parcel"] if c in df.columns), None)
        if asmt_col:
            import requests as _req
            from bs4 import BeautifulSoup as _BS
            _s = _req.Session()
            _s.headers["User-Agent"] = "Mozilla/5.0"
            missing_mask = df[owner_col].isna() | (df[owner_col].astype(str).str.strip().isin(["", "nan", "NAN", "None"]))
            missing_count = missing_mask.sum()
            if missing_count > 0:
                print(f"  [Backfill] Fetching owner names for {missing_count} rows missing assessee_name...")
                for idx in df[missing_mask].index:
                    raw_asmt = str(df.at[idx, asmt_col])
                    compact = re.sub(r"[^0-9]", "", raw_asmt).zfill(12)
                    asr_url = f"{tax_cfg['host']}/mbap/{tax_cfg['county_slug']}/asr/AsrPrint/{compact}"
                    try:
                        r = _s.get(asr_url, timeout=8)
                        if r.status_code == 200:
                            soup = _BS(r.text, "html.parser")
                            for tr in soup.find_all("tr"):
                                cells = tr.find_all(["td", "th"])
                                if len(cells) >= 2:
                                    label = cells[0].get_text(strip=True)
                                    value = cells[1].get_text(strip=True)
                                    if label in ("Assessee Name", "Owner", "Assessee", "Owner Name") and value:
                                        df.at[idx, owner_col] = value
                                        break
                    except Exception:
                        pass
                filled = missing_count - df.loc[missing_mask.index, owner_col].isna().sum()
                print(f"  [Backfill] Filled {filled}/{missing_count} owner names.")
                df.to_csv(input_file, index=False)  # save backfilled names
    # ────────────────────────────────────────────────────────────────────────

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        state_file = os.path.join(base_dir, f"{county}_eagleweb_state.json")

        if os.path.exists(state_file):
            context = browser.new_context(storage_state=state_file)
        else:
            context = browser.new_context()

        page = context.new_page()
        page.add_init_script("""
            const _orig = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                if (delay > 1000) delay = 100;
                return _orig(fn, delay, ...args);
            };
        """)

        print("  Navigating to county portal...")
        page.goto(cfg["login_url"], timeout=60000)
        page.wait_for_load_state("load", timeout=60000)

        if cfg.get("needs_guest_login"):
            if not login_if_needed(page, cfg, state_file):
                print("  Guest login failed.")
                browser.close()
                return

        if cfg.get("has_disclaimer", bool(cfg.get("disclaimer_selector"))):
            ready = ensure_search_ready(page, cfg, state_file)
            if not ready:
                print("  Disclaimer/wall handler failed.")
                browser.close()
                return

            if cfg.get("post_disclaimer_navigate"):
                print(f"  Routing to search page: {cfg['post_disclaimer_navigate']}")
                if cfg.get("use_hash_nav") and cfg.get("search_hash"):
                    # Tyler SPA: use hash navigation to preserve session cookies
                    page.evaluate(f"window.location.hash = '{cfg['search_hash']}'")
                    time.sleep(3)
                else:
                    page.goto(cfg["post_disclaimer_navigate"], timeout=60000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                try:
                    page.wait_for_selector(cfg["search_field"], timeout=15000)
                    print("  Search page ready.")
                except Exception as e:
                    print(f"  Search field not found after routing: {e}")
                    browser.close()
                    return
        else:
            try:
                page.wait_for_selector(cfg["search_field"], timeout=15000)
                print("  Search page ready.")
            except Exception as e:
                print(f"  Search field not found: {e}")
                browser.close()
                return

        print("  Proceeding with automated searches...")

        test_leads = df.copy()
        owner_col = "assessee_name" if "assessee_name" in df.columns else "owner_name"

        for idx, row in test_leads.iterrows():
            owner_name = str(row[owner_col])
            print(f"\n  [{idx}] Processing: {owner_name}")

            raw = owner_name.strip().upper()
            comma_count = raw.count(",")
            if comma_count == 0:
                owners = [raw]
            elif comma_count == 1:
                owners = [raw]
            else:
                owners = [o.strip() for o in raw.split(",") if o.strip()]

            seen_doc_numbers = set()
            seen_lien_texts = set()
            seen_satisfaction_texts = set()
            raw_liens = 0
            raw_satisfactions = 0
            raw_mortgages = 0
            raw_reconveyances = 0
            has_assignment_of_rents = False
            has_affidavit_of_death = False
            ownership_status = "Current"

            for o_name in owners:
                parsed = format_name(o_name)
                if not parsed:
                    continue

                print(f"    -> Searching: '{parsed['lastName']}' / '{parsed['firstName']}' ...", end=" ")

                for attempt in range(3):
                    try:
                        if cfg.get("use_hash_nav") and cfg.get("search_hash"):
                            # Tyler SPA: use hash navigation to avoid killing session
                            page.evaluate(f"window.location.hash = '{cfg['search_hash']}'")
                            time.sleep(2)
                        else:
                            page.goto(cfg["name_search_url"], timeout=30000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                pass
                        break
                    except Exception as nav_err:
                        if attempt == 2:
                            print(f"Navigation failed: {nav_err}")
                        time.sleep(3)

                ready = ensure_search_ready(page, cfg, state_file)
                if not ready:
                    print(f"SKIP — page not ready.")
                    continue

                try:
                    clear_btn = page.locator(cfg["clear_button"])
                    if clear_btn.count() > 0 and clear_btn.first.is_visible(timeout=2000):
                        clear_btn.first.click()
                        time.sleep(0.5)
                except Exception:
                    pass

                try:
                    search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
                    page.fill(cfg["search_field"], search_str, timeout=8000)
                    time.sleep(0.5)
                    force_click = cfg.get("force_search_click", False)
                    page.locator(cfg["search_button"]).first.click(force=force_click)
                    time.sleep(4)
                    try:
                        page.wait_for_selector(cfg["results_selector"], timeout=8000)
                    except Exception:
                        pass

                    soup = BeautifulSoup(page.content(), "html.parser")
                    results = soup.select(cfg["results_selector"])

                    found = 0
                    for row in results:
                        doc_text = row.text.strip().upper()

                        if "NOTICE OF ASSESSMENT LIEN" in doc_text:
                            if re.search(r'GRANTOR\s*\(\d{2,}\)', doc_text):
                                continue

                        doc_num_match = re.search(r'(\d{10})', doc_text)
                        doc_num = doc_num_match.group(1) if doc_num_match else doc_text[:20]
                        is_new_doc = doc_num not in seen_doc_numbers

                        if any(l in doc_text for l in LIEN_TYPES):
                            if doc_text not in seen_lien_texts:
                                seen_lien_texts.add(doc_text)
                                raw_liens += 1
                                found += 1
                        if any(s in doc_text for s in SATISFACTION_TYPES):
                            if doc_text not in seen_satisfaction_texts:
                                seen_satisfaction_texts.add(doc_text)
                                raw_satisfactions += 1
                                found += 1

                        is_assignment = any(a in doc_text for a in ASSIGNMENT_TYPES)
                        if is_assignment:
                            has_assignment_of_rents = True
                        if "AFFIDAVIT OF DEATH" in doc_text:
                            has_affidavit_of_death = True

                        if not is_assignment and is_new_doc:
                            seen_doc_numbers.add(doc_num)
                            if any(m in doc_text for m in MORTGAGE_TYPES):
                                raw_mortgages += 1
                                found += 1
                            if any(r in doc_text for r in RECONVEYANCE_TYPES):
                                raw_reconveyances += 1
                                found += 1

                        if any(d in doc_text for d in DEED_TYPES):
                            if "GRANTOR:" in doc_text:
                                grantor_section = doc_text.split("GRANTOR:")[1].split("GRANTEE:")[0]
                                if parsed['lastName'] in grantor_section:
                                    if "GRANTEE:" in doc_text:
                                        grantee_section = doc_text.split("GRANTEE:")[1]
                                        is_possible_transfer = False
                                        if parsed['lastName'] in grantee_section:
                                            is_possible_transfer = True
                                        elif any(entity_word in grantee_section for entity_word in ["TRUST", "LLC", "INC", "CORP", "FAMILY", "REVOCABLE"]):
                                            if parsed['firstName'] and parsed['firstName'] in grantee_section:
                                                is_possible_transfer = True
                                        if is_possible_transfer:
                                            ownership_status = "Possible Transfer"
                                        else:
                                            ownership_status = "Sold / Transfer Detected"
                                    else:
                                        ownership_status = "Sold / Transfer Detected"

                    print(f"found {found} new relevant docs.")
                except Exception as e:
                    print(f"FAILED ({type(e).__name__}: {e})")

            df.at[idx, "active_liens"] = max(0, raw_liens - raw_satisfactions)
            df.at[idx, "mortgages"] = max(0, raw_mortgages - raw_reconveyances)
            df.at[idx, "ownership_status"] = ownership_status
            df.at[idx, "has_assignment_of_rents"] = has_assignment_of_rents
            df.at[idx, "has_affidavit_of_death"] = has_affidavit_of_death
            df.to_csv(output_file, index=False)

        browser.close()

    df.to_csv(output_file, index=False)
    print(f"\n[Stage 7] Enrichment Complete. Saved to {output_file}")


if __name__ == "__main__":
    county_arg = sys.argv[1] if len(sys.argv) > 1 else "tehama"
    scrape_liens(county_arg)
