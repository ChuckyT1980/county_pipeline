"""
Run the real owner_resolve.py cascade against Kern's genuinely-active
parcel batch. No record ships with a "partially verified" label — a
result either gets a real recorder name-confirmation, or it goes into
the needs-further-enrichment list (Google dork URLs for manual lookup,
or a candidate for a paid skip-trace/people-search service) instead of
being shipped at all.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
from owner_resolve import build_dork_enrichment, resolve_from_kern_recorder

SCRATCH = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad"
BATCH = f"{SCRATCH}/kern_real_batch_merged.csv"
CONFIRMED_OUT = f"{SCRATCH}/kern_owner_confirmed.csv"
NEEDS_ENRICHMENT_OUT = f"{SCRATCH}/kern_owner_needs_enrichment.csv"


def main(limit=None):
    with open(BATCH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    active = [r for r in rows if r["likely_already_transferred"] != "True"]
    if limit:
        active = active[:limit]

    confirmed = []
    needs_enrichment = []

    for i, row in enumerate(active):
        apn = row["apn"]
        candidate_name = (row.get("owner_from_source_list") or "").strip()
        print(f"[{i+1}/{len(active)}] {apn} ({candidate_name or 'NO CANDIDATE'}) ...", end=" ")

        if not candidate_name:
            print("needs enrichment (no candidate name from source list)")
            dorks = build_dork_enrichment(apn, "kern")["dorks"]
            needs_enrichment.append({"apn": apn, "candidate_name": "", "reason": "no candidate name available", "dork_urls": " | ".join(d["search_url"] for d in dorks)})
            continue

        try:
            rec = resolve_from_kern_recorder(candidate_name)
        except Exception as e:
            print(f"ERROR: {e}")
            dorks = build_dork_enrichment(apn, "kern")["dorks"]
            needs_enrichment.append({"apn": apn, "candidate_name": candidate_name, "reason": f"recorder lookup error: {e}", "dork_urls": " | ".join(d["search_url"] for d in dorks)})
            continue

        if rec and rec.get("verification") == "CONFIRMED_IN_RECORDER_INDEX" and rec.get("owner_name"):
            print(f"CONFIRMED: {rec['owner_name']}")
            confirmed.append({
                "apn": apn,
                "owner_name": rec["owner_name"],
                "net_taxable_value": row.get("net_taxable_value"),
                "situs": row.get("situs"),
                "recorder_source_url": rec.get("source_url"),
                "recorder_verification": rec["verification"],
                "recorder_caveat": rec.get("note"),
            })
        else:
            reason = rec.get("verification") if rec else "recorder lookup failed"
            print(f"needs enrichment ({reason})")
            dorks = build_dork_enrichment(apn, "kern")["dorks"]
            needs_enrichment.append({"apn": apn, "candidate_name": candidate_name, "reason": reason, "dork_urls": " | ".join(d["search_url"] for d in dorks)})

    if confirmed:
        with open(CONFIRMED_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(confirmed[0].keys()))
            w.writeheader()
            w.writerows(confirmed)

    if needs_enrichment:
        with open(NEEDS_ENRICHMENT_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(needs_enrichment[0].keys()))
            w.writeheader()
            w.writerows(needs_enrichment)

    print(f"\nDone. {len(confirmed)} recorder-confirmed, {len(needs_enrichment)} need further enrichment (of {len(active)} attempted).")
    print(f"Confirmed: {CONFIRMED_OUT}")
    print(f"Needs enrichment: {NEEDS_ENRICHMENT_OUT}")


if __name__ == "__main__":
    import sys as _sys
    lim = int(_sys.argv[1]) if len(_sys.argv) > 1 else None
    main(limit=lim)
