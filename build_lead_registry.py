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
SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_cycle_lookup():
    """
    Load county-sale-cycle-registry.csv as the SINGLE source of truth for
    sale-cycle metadata - no hardcoded per-county dict duplicating it here.
    Keyed by (county_lower, claim_deadline) since that's what a dossier
    carries; this generically handles counties with multiple distinct
    cycles (Madera, Nevada) the same way as single-cycle counties. Colusa
    is per-parcel deadlines, not one cycle-wide date, so it's matched by
    county alone (single row covers all its parcels).
    """
    lookup = {}
    colusa_row = None
    if not CYCLE_REGISTRY.exists():
        return lookup, colusa_row
    with open(CYCLE_REGISTRY, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            county_key = row["county"].lower().replace(" ", "_")
            cycle = {
                "sale_cycle_id": row["sale_cycle_id"],
                "source_artifact_id": row["source_artifact_id"],
                "source_document_date": row["source_document_date"],
                "lifecycle_status": row["lifecycle_status"],
            }
            if county_key == "colusa":
                colusa_row = cycle
                continue
            lookup[(county_key, row["claim_deadline"])] = cycle
    return lookup, colusa_row


def parse_dossier(path):
    text = path.read_text(encoding="utf-8")
    def grab(pat, default=None):
        m = re.search(pat, text)
        return m.group(1).strip() if m else default
    # Parse the real county name out of the dossier's own "**County**: X
    # County, California" line rather than guessing from the filename -
    # filename-splitting on "_" silently mis-parses any multi-word CA
    # county (San Joaquin -> "san", Del Norte -> "del", Los Angeles,
    # Santa Clara, Contra Costa, El Dorado, San Diego, ...). This was a
    # real bug twice (San Joaquin, then Del Norte) before being fixed at
    # the root instead of patched one county at a time.
    county_display = grab(r"\*\*County\*\*:\s*([^,]+?)\s+County,")
    county = county_display.lower().replace(" ", "_") if county_display else path.name.split("_")[0]
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
    cycle_lookup, colusa_cycle = load_cycle_lookup()

    rows = []
    parser_errors = []
    input_artifacts = set()
    unmatched_dossiers = []

    for path in sorted(DASHBOARD.glob("*_excess_claim.md")):
        try:
            county, apn, deadline, amount = parse_dossier(path)
        except Exception as e:
            parser_errors.append({"file": str(path), "error": str(e)})
            continue

        if county == "colusa":
            cycle = colusa_cycle
        else:
            cycle = cycle_lookup.get((county, deadline))
        if not cycle:
            # No cycle in the registry matches this county+deadline combo -
            # do NOT silently invent one. Flag it and skip rather than
            # guess a sale_cycle_id, per the verified-or-excluded rule.
            unmatched_dossiers.append({"file": str(path), "county": county, "deadline": deadline})
            parser_errors.append({
                "file": str(path),
                "error": f"No matching sale cycle in county-sale-cycle-registry.csv for county={county!r} deadline={deadline!r} - excluded, not guessed",
            })
            continue
        input_artifacts.add(cycle["source_artifact_id"])

        # source_verified means a real, hashable artifact was actually
        # captured and preserved - not just that a URL was cited. A cycle
        # whose source_artifact_id isn't a real sha256 (e.g. Sonoma, whose
        # scraped results page was never saved to disk) has NOT earned
        # SOURCE_VERIFIED, regardless of how confident the extracted rows
        # look - this is the state machine's own gate, not a bolt-on.
        cycle_source_verified = bool(SHA256_ID_RE.match(cycle["source_artifact_id"]))

        amount_disclosed = bool(amount) and "UNDISCLOSED" not in (amount or "")
        evaluation = evaluate_lead(
            source_verified=cycle_source_verified,
            deadline_raw=deadline,
            run_date=AS_OF,
            amount_disclosed=amount_disclosed,
            cycle_expired=cycle["lifecycle_status"] == "EXPIRED",
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
