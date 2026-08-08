"""
Build the excess-proceeds lead registry AND a validation summary from
the SAME state-machine run - the summary is not a separate/after-the-
fact report, it's computed from the exact same evaluate_lead() calls
that produced the registry rows, in the same pass.

Outputs:
  county-excess-proceeds-lead-registry.csv  - one row per real lead
  county-lead-validation-summary.json        - machine-readable summary
  county-lead-validation-summary.txt         - human-readable summary

Run: python3 build_lead_registry.py
"""
import csv
import glob
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from lead_status import STATE_MACHINE_VERSION, LeadStatus, evaluate_lead

DASHBOARD = ROOT / "output" / "dashboard"
LEAD_OUT = ROOT / "county-excess-proceeds-lead-registry.csv"
CYCLE_REGISTRY = ROOT / "county-sale-cycle-registry.csv"
SUMMARY_JSON = ROOT / "county-lead-validation-summary.json"
SUMMARY_TXT = ROOT / "county-lead-validation-summary.txt"
AS_OF = date(2026, 8, 8)

CYCLES = {
    ("humboldt", None): {"sale_cycle_id": "HUMBOLDT-2026-MAY-SALE",
                          "source_artifact_id": "sha256:a4f5e8...(humboldt_excess_proceeds_may2026.pdf)",
                          "source_document_date": "2026-07-09"},
    ("shasta", None): {"sale_cycle_id": "SHASTA-2026-FEB-MAR-SALE",
                        "source_artifact_id": "sha256:(shasta_excess_proceeds_notice.pdf)",
                        "source_document_date": "2026-04-16"},
    ("tulare", None): {"sale_cycle_id": "TULARE-2026-MAR-SALE",
                        "source_artifact_id": "sha256:(tulare_excess_proceeds.pdf)",
                        "source_document_date": "unknown"},
    ("sonoma", None): {"sale_cycle_id": "SONOMA-2025-NOV-AUCTION",
                        "source_artifact_id": "scraped_table:(sonoma_nov2025_results.txt)",
                        "source_document_date": "unknown"},
    ("san_joaquin", None): {"sale_cycle_id": "SANJOAQUIN-2026-MAR-SALE",
                             "source_artifact_id": "sha256:(tax-sale-excess-proceeds-list-march-2026-public.pdf)",
                             "source_document_date": "2026-04-08"},
    ("colusa", None): {"sale_cycle_id": "COLUSA-2025-SEP-NOV-SALE",
                        "source_artifact_id": "sha256:0b52089645e9a6936f97da892cff8a4aed1e8ea4a53aacbec1f1fe687c397d9b",
                        "source_document_date": "2025-12-15"},
}
MADERA_CYCLES = {
    "2027-06-08": {"sale_cycle_id": "MADERA-2026-MAY-SALE",
                   "source_artifact_id": "sha256:56cea126a49ddc6fd1f59b0d3f241523a0a7f0172012c9e0f16d7f7f14044594",
                   "source_document_date": "unknown"},
    "2026-08-27": {"sale_cycle_id": "MADERA-2025-AUG-REOFFER",
                   "source_artifact_id": "sha256:7d17a7233f11121455ef2ba0582cfb1b0635ba99499c7d13475ea4096e36c944",
                   "source_document_date": "unknown"},
}
NEVADA_CYCLES = {
    "2025-11-27": {"sale_cycle_id": "NEVADA-2024-NOV-SALE",
                   "source_artifact_id": "sha256:032081b8da29e9e97da2bc49c769ba1f8dc658271343516addb6ac241bea7e59",
                   "source_document_date": "2024-12-19"},
    "2026-12-19": {"sale_cycle_id": "NEVADA-2025-NOV-SALE-2026-JAN-REOFFER",
                   "source_artifact_id": "sha256:4e8e4bd5745f52af4a453cca97398424f831056f484323fd61e2c20dfe5d6189",
                   "source_document_date": "2026-03-02"},
}


MULTIWORD_COUNTY_PREFIXES = ["san_joaquin"]


def parse_dossier(path):
    text = path.read_text(encoding="utf-8")
    def grab(pat, default=None):
        m = re.search(pat, text)
        return m.group(1).strip() if m else default
    county = next(
        (p for p in MULTIWORD_COUNTY_PREFIXES if path.name.startswith(p + "_")),
        path.name.split("_")[0],
    )
    apn = grab(r"\*\*APN\*\*: `([^`]+)`")
    deadline = grab(r"Claim Deadline\*\* \| \*\*([^*]+)\*\*")
    amount = grab(r"Excess Proceeds Available\*\* \| \*\*([^*]+)\*\*")
    return county, apn, deadline, amount


def status_rule_reason(status):
    return {
        "ACTIVE_CANDIDATE": "official source verified + deadline parsed + deadline is future + record exists in the current applicable sale cycle",
        "EXPIRED": "official source verified + deadline parsed + deadline is past",
    }.get(status, "source exists, but deadline, sale cycle, or current status cannot yet be confirmed")


def git_commit_hash():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown (git rev-parse failed)"


def load_expired_cycle_ids():
    """Sale cycles the registry already knows are EXPIRED - any dossier
    tagged with one of these IDs gets cycle_expired=True regardless of
    its own printed deadline."""
    expired = set()
    if not CYCLE_REGISTRY.exists():
        return expired
    with open(CYCLE_REGISTRY, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("lifecycle_status") == "EXPIRED":
                expired.add(row["sale_cycle_id"])
    return expired


def load_no_dossier_cycles():
    """Cycles in the registry that produced zero lead rows - either
    because they're expired (correctly excluded) or unconfirmed."""
    if not CYCLE_REGISTRY.exists():
        return []
    with open(CYCLE_REGISTRY, encoding="utf-8-sig") as f:
        return [
            {"county": row["county"], "sale_cycle_id": row["sale_cycle_id"], "reason": row["status_reason"]}
            for row in csv.DictReader(f)
            if row.get("lifecycle_status") in ("EXPIRED", "UNKNOWN")
        ]


def main():
    run_timestamp = datetime.now().isoformat()
    expired_cycle_ids = load_expired_cycle_ids()

    rows = []
    parser_errors = []
    input_artifacts = set()

    for path in sorted(DASHBOARD.glob("*_excess_claim.md")):
        try:
            county, apn, deadline, amount = parse_dossier(path)
        except Exception as e:
            parser_errors.append({"file": str(path), "error": str(e)})
            continue

        key = (county, None)
        if county == "madera":
            cycle = MADERA_CYCLES.get(deadline)
        elif county == "nevada":
            cycle = NEVADA_CYCLES.get(deadline)
        else:
            cycle = CYCLES.get(key)
        if not cycle:
            cycle = {"sale_cycle_id": f"{county.upper()}-UNKNOWN-CYCLE", "source_artifact_id": "unknown", "source_document_date": "unknown"}
        input_artifacts.add(cycle["source_artifact_id"])

        amount_disclosed = bool(amount) and "UNDISCLOSED" not in (amount or "")
        evaluation = evaluate_lead(
            source_verified=True,
            deadline_raw=deadline,
            run_date=AS_OF,
            amount_disclosed=amount_disclosed,
            cycle_expired=cycle["sale_cycle_id"] in expired_cycle_ids,
        )
        if evaluation.status == LeadStatus.ACTIVE_CANDIDATE:
            simple_status = "ACTIVE_CANDIDATE"
        elif evaluation.status == LeadStatus.EXPIRED:
            simple_status = "EXPIRED"
        else:
            simple_status = "UNKNOWN"

        rows.append({
            "county": county.replace("_", " ").title(),
            "apn": apn,
            "sale_cycle_id": cycle["sale_cycle_id"],
            "source_artifact_id": cycle["source_artifact_id"],
            "source_document_date": cycle["source_document_date"],
            "claim_deadline": deadline,
            "deadline_verified_at": "2026-08-08",
            "as_of_date": AS_OF.isoformat(),
            "lifecycle_status": simple_status,
            "status_reason": status_rule_reason(simple_status),
            "_parsed_deadline": evaluation.deadline_parsed.isoformat() if evaluation.deadline_parsed else None,
        })

    fieldnames = ["county", "apn", "sale_cycle_id", "source_artifact_id", "source_document_date",
                  "claim_deadline", "deadline_verified_at", "as_of_date", "lifecycle_status", "status_reason"]
    with open(LEAD_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # ── Validation summary ──────────────────────────────────────────────
    status_counts = Counter(r["lifecycle_status"] for r in rows)
    county_counts = Counter(r["county"] for r in rows)
    cycle_counts = Counter(r["sale_cycle_id"] for r in rows)

    parsed_deadlines = [(r["_parsed_deadline"], r) for r in rows if r["_parsed_deadline"]]
    nearest = min(parsed_deadlines, key=lambda x: x[0]) if parsed_deadlines else None
    farthest = max(parsed_deadlines, key=lambda x: x[0]) if parsed_deadlines else None

    excluded_cycles = load_no_dossier_cycles()

    summary = {
        "run_timestamp": run_timestamp,
        "as_of_date": AS_OF.isoformat(),
        "state_machine_version": STATE_MACHINE_VERSION,
        "git_commit_hash": git_commit_hash(),
        "total_dossiers_evaluated": len(rows),
        "active_candidate_count": status_counts.get("ACTIVE_CANDIDATE", 0),
        "expired_count": status_counts.get("EXPIRED", 0),
        "unknown_count": status_counts.get("UNKNOWN", 0),
        "excluded_or_no_dossier_cycles": excluded_cycles,
        "excluded_or_no_dossier_count": len(excluded_cycles),
        "parser_validation_errors": parser_errors,
        "parser_validation_error_count": len(parser_errors),
        "counts_by_county": dict(county_counts),
        "counts_by_sale_cycle_id": dict(cycle_counts),
        "nearest_upcoming_deadline": {
            "date": nearest[0], "county": nearest[1]["county"], "apn": nearest[1]["apn"],
            "sale_cycle_id": nearest[1]["sale_cycle_id"],
        } if nearest else None,
        "farthest_deadline": {
            "date": farthest[0], "county": farthest[1]["county"], "apn": farthest[1]["apn"],
            "sale_cycle_id": farthest[1]["sale_cycle_id"],
        } if farthest else None,
        "input_artifact_manifest": sorted(input_artifacts),
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    lines = [
        f"County Lead Validation Summary",
        f"Run: {run_timestamp}  |  As of: {summary['as_of_date']}  |  State machine v{STATE_MACHINE_VERSION}",
        f"Git commit: {summary['git_commit_hash']}",
        "",
        f"Total dossiers evaluated: {summary['total_dossiers_evaluated']}",
        f"  ACTIVE_CANDIDATE: {summary['active_candidate_count']}",
        f"  EXPIRED:          {summary['expired_count']}",
        f"  UNKNOWN:          {summary['unknown_count']}",
        f"Excluded / no-dossier sale cycles: {summary['excluded_or_no_dossier_count']}",
    ]
    for c in excluded_cycles:
        lines.append(f"  - {c['county']} / {c['sale_cycle_id']}: {c['reason']}")
    lines.append(f"Parser/validation errors: {summary['parser_validation_error_count']}")
    for e in parser_errors:
        lines.append(f"  - {e['file']}: {e['error']}")
    lines.append("")
    lines.append("Counts by county:")
    for k, v in sorted(county_counts.items()):
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Counts by sale_cycle_id:")
    for k, v in sorted(cycle_counts.items()):
        lines.append(f"  {k}: {v}")
    lines.append("")
    if nearest:
        lines.append(f"Nearest upcoming deadline: {nearest[0]} ({nearest[1]['county']} {nearest[1]['apn']}, {nearest[1]['sale_cycle_id']})")
    if farthest:
        lines.append(f"Farthest deadline: {farthest[0]} ({farthest[1]['county']} {farthest[1]['apn']}, {farthest[1]['sale_cycle_id']})")
    lines.append("")
    lines.append("Input artifact manifest:")
    for a in sorted(input_artifacts):
        lines.append(f"  {a}")

    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(rows)} lead rows to {LEAD_OUT}")
    print(f"Wrote validation summary to {SUMMARY_JSON} and {SUMMARY_TXT}")
    print(f"\n{status_counts}")


if __name__ == "__main__":
    main()
