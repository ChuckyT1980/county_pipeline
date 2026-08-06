"""
Recompute verification_score directly from CSV field completeness.

Previous approach pulled the score from parcel_verifications (latest run),
which meant later runs with different source expectations (e.g. environmental
enrichment failing on rural APNs) could overwrite an earlier complete score.

New approach: score = percentage of key delivered fields that have real
values in the CSV. Reflects what a buyer actually sees.

Key fields tracked (each worth 100 / n_fields):
    verified_current_owner_name  (owner known)
    mailing_address              (direct-mail ready)
    situs_address                (property location)
    recorder_doc_numbers         (verifiable at recorder)
    total_tax_billed             (tax bill fetched)
    land_value                   (assessed value)
    flood_zone                   (FEMA — only if geocoded, so partial)
    fire_hazard_zone             (CalFire — same)
"""
import argparse
import pandas as pd


TRACKED_FIELDS = [
    "verified_current_owner_name",
    "mailing_address",
    "situs_address",
    "recorder_doc_numbers",
    "total_tax_billed",
    "land_value",
    "flood_zone",
    "fire_hazard_zone",
]


def _has_value(v):
    if v is None or pd.isna(v):
        return False
    s = str(v).strip().lower()
    return s not in {"", "nan", "none", "unmapped"}


def recompute(csv_path: str) -> dict:
    df = pd.read_csv(csv_path, dtype=str)
    n_fields = len(TRACKED_FIELDS)

    scores = []
    for _, row in df.iterrows():
        present = sum(_has_value(row.get(f)) for f in TRACKED_FIELDS)
        pct = round(100 * present / n_fields)
        scores.append(pct)

    df["verification_score"] = [str(s) for s in scores]
    df.to_csv(csv_path, index=False)

    # Stats
    dist = pd.Series(scores).value_counts().sort_index()
    print(f"Recomputed verification_score for {len(df)} rows.")
    print(f"Field coverage per row (out of {n_fields} fields tracked):")
    for k, v in dist.items():
        pct_of_max = k
        print(f"  score={pct_of_max:>3}%  count={v}")
    print(f"  Average: {sum(scores)/len(scores):.1f}%")
    return {"n_rows": len(df), "avg_score": sum(scores)/len(scores)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    args = p.parse_args()
    recompute(args.csv_path)
