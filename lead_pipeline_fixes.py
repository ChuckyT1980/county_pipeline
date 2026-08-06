"""
lead_pipeline_fixes.py

Drop-in fixes for the tax-delinquent lead pipeline, based on issues found
in the northern_ca_MASTER_export_with_owners.csv and northern_ca_export_ready.csv
exports (Tehama/Shasta county adapters).

Five independent pieces -- use whichever apply to your pipeline stage:

1. resolve_owner_name()      -- defensive owner_name backfill so
                                 "SKIP_TRACE_REQUIRED" never leaks into an
                                 export when a real assessor-roll name exists.
2. classify_entity_owner()   -- flags LLC/Trust/Corp/Association owners so
                                 they can be split from individual homeowners
                                 (different buyer pool, different urgency).
3. flag_clean_title()        -- simple no-lien / no-mortgage boolean.
4. audit_recorder_doc_coverage() -- per-county completeness check on
                                 rec_doc_number / rec_doc_date, so a county
                                 adapter silently going empty gets caught at
                                 build time instead of by a buyer.
5. diff_exports()            -- compares two successive export CSVs by APN
                                 and reports what got dropped, added, or
                                 re-tiered between runs. This is what would
                                 have caught the 7 Shasta leads (Drake, Jones,
                                 Wait, Kutras, Clearwater, Garner, Meadow Ridge)
                                 disappearing between the two files you sent.

All functions take/return plain pandas DataFrames so you can drop them into
whichever stage of the pipeline currently does this work.
"""

import re
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Owner name backfill
# ---------------------------------------------------------------------------

PLACEHOLDER = "SKIP_TRACE_REQUIRED"


def resolve_owner_name(df: pd.DataFrame,
                        owner_col: str = "owner_name",
                        assessee_col: str = "assessee_name") -> pd.DataFrame:
    """
    Ensure owner_col never exports as a literal placeholder when a real
    assessor-roll name (assessee_col) is available.

    Adds:
        owner_name        -- backfilled value (overwrites in place)
        owner_name_source  -- "Already Resolved" | "Assessor Roll (backfilled)"
                              | "Needs Skip Trace"

    This is the fix for the bug where 187/198 rows exported with
    owner_name == "SKIP_TRACE_REQUIRED" even though 100 of those rows had
    a real name sitting in assessee_name the whole time.
    """
    df = df.copy()
    if assessee_col not in df.columns:
        # Nothing to backfill from -- just tag what's still unresolved.
        df["owner_name_source"] = df[owner_col].apply(
            lambda v: "Needs Skip Trace" if v == PLACEHOLDER else "Already Resolved"
        )
        return df

    def _resolve(row):
        if row[owner_col] != PLACEHOLDER:
            return row[owner_col], "Already Resolved"
        if row[assessee_col] != PLACEHOLDER and pd.notna(row[assessee_col]):
            return row[assessee_col], "Assessor Roll (backfilled)"
        return PLACEHOLDER, "Needs Skip Trace"

    resolved = df.apply(_resolve, axis=1, result_type="expand")
    df[owner_col] = resolved[0]
    df["owner_name_source"] = resolved[1]
    return df


# ---------------------------------------------------------------------------
# 2. Entity vs. individual owner classification
# ---------------------------------------------------------------------------

ENTITY_PATTERN = re.compile(
    r"\b(?:LLC|INC|ASSOCIATION|TRUST|CORP|CORPORATION|FUELS|LP|LTD|CO\.?)\b",
    re.IGNORECASE,
)


def classify_entity_owner(df: pd.DataFrame, owner_col: str = "owner_name") -> pd.DataFrame:
    """
    Adds is_entity (bool) -- True if the owner name matches an
    LLC/Inc/Trust/Corp/Association/etc. pattern.

    Use this to split individual homeowners (real distress, primary wholesale
    buyer pool) from corporate/trust/association owners (different buyer
    pool, usually lower urgency -- e.g. RANCHO TEHAMA ASSOCIATION with a
    $287 balance is an HOA paperwork issue, not a motivated seller).
    """
    df = df.copy()
    df["is_entity"] = df[owner_col].astype(str).str.contains(ENTITY_PATTERN, na=False)
    return df


# ---------------------------------------------------------------------------
# 3. Clean title flag
# ---------------------------------------------------------------------------

def flag_clean_title(df: pd.DataFrame,
                      liens_col: str = "active_liens",
                      mortgage_col: str = "mortgages") -> pd.DataFrame:
    """
    Adds clean_title (bool) -- True only if BOTH active_liens == 0 and
    mortgages == 0. Use this instead of eyeballing lien counts -- it's what
    should gate any "no liens" claim in a buyer-facing sheet.
    """
    df = df.copy()
    df["clean_title"] = (df[liens_col] == 0) & (df[mortgage_col] == 0)
    return df


# ---------------------------------------------------------------------------
# 4. Recorder document completeness audit
# ---------------------------------------------------------------------------

def audit_recorder_doc_coverage(df: pd.DataFrame,
                                 county_col: str = "county",
                                 doc_number_col: str = "rec_doc_number",
                                 doc_date_col: str = "rec_doc_date",
                                 min_coverage: float = 0.5) -> pd.DataFrame:
    """
    Per-county completeness check on recorder document fields. Returns a
    summary DataFrame and prints a warning for any county below
    min_coverage on either field.

    This would have caught: rec_doc_number was 0% populated for every
    Tehama row and 100% populated for every Shasta row in the same export --
    a silent per-adapter gap, not random missing data. rec_doc_date was
    0% populated across BOTH counties, which points to a field that isn't
    wired up at all yet.
    """
    rows = []
    for county, group in df.groupby(county_col):
        n = len(group)
        num_cov = group[doc_number_col].notna().mean() if doc_number_col in group else 0.0
        date_cov = group[doc_date_col].notna().mean() if doc_date_col in group else 0.0
        rows.append({
            "county": county,
            "n_leads": n,
            "rec_doc_number_coverage": round(num_cov, 2),
            "rec_doc_date_coverage": round(date_cov, 2),
        })
        if num_cov < min_coverage:
            print(f"[WARN] {county}: rec_doc_number only {num_cov:.0%} populated "
                  f"({n} leads) -- adapter may not be capturing this field.")
        if date_cov < min_coverage:
            print(f"[WARN] {county}: rec_doc_date only {date_cov:.0%} populated "
                  f"({n} leads) -- adapter may not be capturing this field.")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Export diff checker
# ---------------------------------------------------------------------------

def diff_exports(old_path: str,
                  new_path: str,
                  key_col: str = "apn",
                  tier_col: str = "Export_Tier",
                  balance_col: str = "total_balance") -> dict:
    """
    Compares two export CSVs by key_col (default: apn) and reports:
        dropped   -- rows in old_path not present in new_path
        added     -- rows in new_path not present in old_path
        retiered  -- rows present in both where tier_col changed

    Run this after every pipeline run, before the file goes out the door.
    It's the systematic version of manually noticing that 7 Shasta leads
    (including 3 clean-title, $8K-9K balance leads) silently disappeared
    between two exports.

    Returns a dict with three DataFrames: {"dropped", "added", "retiered"}.
    Also prints a one-line summary.
    """
    old = pd.read_csv(old_path)
    new = pd.read_csv(new_path)

    old_keys = set(old[key_col])
    new_keys = set(new[key_col])

    dropped_keys = old_keys - new_keys
    added_keys = new_keys - old_keys
    common_keys = old_keys & new_keys

    dropped = old[old[key_col].isin(dropped_keys)].copy()
    added = new[new[key_col].isin(added_keys)].copy()

    retiered_rows = []
    if tier_col in old.columns and tier_col in new.columns:
        old_idx = old.set_index(key_col)
        new_idx = new.set_index(key_col)
        for k in common_keys:
            old_tier = old_idx.loc[k, tier_col] if k in old_idx.index else None
            new_tier = new_idx.loc[k, tier_col] if k in new_idx.index else None
            if pd.isna(old_tier):
                old_tier = None
            if pd.isna(new_tier):
                new_tier = None
            if old_tier != new_tier:
                retiered_rows.append({
                    key_col: k,
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                })
    retiered = pd.DataFrame(retiered_rows)

    print(f"[DIFF] {len(dropped)} dropped, {len(added)} added, "
          f"{len(retiered)} re-tiered between {old_path} -> {new_path}")

    if len(dropped) and balance_col in dropped.columns:
        lost_balance = dropped[balance_col].sum()
        print(f"[DIFF] Dropped rows represent ${lost_balance:,.2f} in total_balance -- "
              f"review before treating this export as final.")

    return {"dropped": dropped, "added": added, "retiered": retiered}
