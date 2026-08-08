"""
Release gate for the excess-proceeds lead inventory.

Run AFTER build_lead_registry.py, BEFORE any outreach/sale of leads.
Fails loudly (nonzero exit) if any assertion below does not hold — this
script is the actual enforcement mechanism, not just documentation of
intent.

Assertions:
  1. Every ACTIVE_CANDIDATE row has a nonempty sale_cycle_id.
  2. Every ACTIVE_CANDIDATE row has a real source artifact hash
     (sha256:<64 hex chars> - not a placeholder string, not empty,
     not "NO ARTIFACT PRESERVED").
  3. Every ACTIVE_CANDIDATE row has a future parsed claim_deadline
     (re-parsed and re-checked here, not trusted from the CSV column).
  4. Every ACTIVE_CANDIDATE row's (county, sale_cycle_id) pair exists
     in county-sale-cycle-registry.csv and that registry row's own
     county field matches (deadline is linked to the correct county
     and cycle, not just any cycle with a matching date).
  5. No WIRING-TEST / test-fixture identifier appears anywhere in
     dashboard_feed.json.
  6. No EXPIRED or UNKNOWN sale_cycle_id (per the registry) appears in
     any dossier file, dashboard_feed.json entry, ACTIVE_CANDIDATE lead
     row, or buyer export.

Run: python3 release_gate.py
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from lead_status import _try_parse_date

LEAD_REGISTRY = ROOT / "county-excess-proceeds-lead-registry.csv"
CYCLE_REGISTRY = ROOT / "county-sale-cycle-registry.csv"
FEED_FILE = ROOT / "output" / "dashboard" / "dashboard_feed.json"
DASHBOARD_DIR = ROOT / "output" / "dashboard"
BUYER_EXPORTS = [ROOT / "output" / "active_buyers_intelligence.csv", ROOT / "tax_pipeline" / "butte_repeat_buyers.csv"]
AS_OF = date(2026, 8, 8)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_lead_rows():
    with open(LEAD_REGISTRY, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_cycle_registry():
    with open(CYCLE_REGISTRY, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def check_1_nonempty_sale_cycle_id(active_rows):
    failures = [r for r in active_rows if not r.get("sale_cycle_id", "").strip()]
    return "Every ACTIVE_CANDIDATE has a nonempty sale_cycle_id", failures, [
        f"{r['county']} {r['apn']}: sale_cycle_id is empty" for r in failures
    ]


def check_2_real_artifact_hash(active_rows):
    failures = [r for r in active_rows if not SHA256_RE.match(r.get("source_artifact_id", ""))]
    return "Every ACTIVE_CANDIDATE has a real source artifact hash (sha256:<64 hex>)", failures, [
        f"{r['county']} {r['apn']}: source_artifact_id = {r.get('source_artifact_id')!r} (not a valid sha256)" for r in failures
    ]


def check_3_future_deadline(active_rows):
    failures = []
    details = []
    for r in active_rows:
        parsed = _try_parse_date(r.get("claim_deadline", ""))
        if parsed is None:
            failures.append(r)
            details.append(f"{r['county']} {r['apn']}: claim_deadline {r.get('claim_deadline')!r} does not parse")
        elif parsed <= AS_OF:
            failures.append(r)
            details.append(f"{r['county']} {r['apn']}: claim_deadline {parsed.isoformat()} is not in the future as of {AS_OF.isoformat()}")
    return "Every ACTIVE_CANDIDATE has a future, re-parsed claim deadline", failures, details


def check_4_deadline_linked_to_correct_cycle(active_rows, cycle_rows):
    cycle_by_id = {c["sale_cycle_id"]: c for c in cycle_rows}
    failures = []
    details = []
    for r in active_rows:
        cid = r.get("sale_cycle_id", "")
        cycle = cycle_by_id.get(cid)
        if cycle is None:
            failures.append(r)
            details.append(f"{r['county']} {r['apn']}: sale_cycle_id {cid!r} not found in county-sale-cycle-registry.csv at all")
            continue
        if cycle["county"].strip().lower() != r["county"].strip().lower():
            failures.append(r)
            details.append(
                f"{r['county']} {r['apn']}: sale_cycle_id {cid!r} belongs to registry county "
                f"{cycle['county']!r}, not {r['county']!r} - county/cycle mismatch"
            )
            continue
        if cycle["lifecycle_status"] != "ACTIVE_CANDIDATE":
            failures.append(r)
            details.append(
                f"{r['county']} {r['apn']}: sale_cycle_id {cid!r} registry status is "
                f"{cycle['lifecycle_status']!r}, not ACTIVE_CANDIDATE - lead should not be active"
            )
    return "Every ACTIVE_CANDIDATE's sale_cycle_id resolves to the correct, active county cycle", failures, details


def check_5_no_test_fixtures_in_feed():
    failures = []
    if FEED_FILE.exists():
        feed = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        for e in feed:
            blob = json.dumps(e).upper()
            if "WIRING-TEST" in blob or "TEST_COUNTY" in blob or "TEST-FIXTURE" in blob:
                failures.append(e)
    details = [f"dashboard_feed.json entry apn={e.get('apn')!r} county={e.get('county')!r} contains a test identifier" for e in failures]
    return "No WIRING-TEST / test-fixture identifier appears in dashboard_feed.json", failures, details


def check_6_excluded_cycles_dont_leak(cycle_rows):
    excluded_ids = {c["sale_cycle_id"] for c in cycle_rows if c["lifecycle_status"] in ("EXPIRED", "UNKNOWN")}
    failures = []
    details = []

    # a) dossiers
    for path in sorted(DASHBOARD_DIR.glob("*_excess_claim.md")):
        text = path.read_text(encoding="utf-8")
        for cid in excluded_ids:
            if cid in text:
                failures.append(path)
                details.append(f"dossier {path.name} references excluded sale_cycle_id {cid!r}")

    # b) dashboard feed
    if FEED_FILE.exists():
        feed_text = FEED_FILE.read_text(encoding="utf-8")
        for cid in excluded_ids:
            if cid in feed_text:
                failures.append(FEED_FILE)
                details.append(f"dashboard_feed.json references excluded sale_cycle_id {cid!r}")

    # c) lead registry ACTIVE rows (checked separately, more strictly, by check_4 too)
    with open(LEAD_REGISTRY, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["lifecycle_status"] == "ACTIVE_CANDIDATE" and r["sale_cycle_id"] in excluded_ids:
                failures.append(r)
                details.append(f"lead registry row {r['county']} {r['apn']} is ACTIVE_CANDIDATE but cites excluded cycle {r['sale_cycle_id']!r}")

    # d) buyer exports
    for bexp in BUYER_EXPORTS:
        if not bexp.exists():
            continue
        text = bexp.read_text(encoding="utf-8")
        for cid in excluded_ids:
            if cid in text:
                failures.append(bexp)
                details.append(f"buyer export {bexp.name} references excluded sale_cycle_id {cid!r}")

    return (
        f"No excluded cycle ({', '.join(sorted(excluded_ids))}) appears in any dossier, feed, lead row, or buyer export",
        failures,
        details,
    )


def main():
    lead_rows = load_lead_rows()
    active_rows = [r for r in lead_rows if r["lifecycle_status"] == "ACTIVE_CANDIDATE"]
    cycle_rows = load_cycle_registry()

    checks = [
        check_1_nonempty_sale_cycle_id(active_rows),
        check_2_real_artifact_hash(active_rows),
        check_3_future_deadline(active_rows),
        check_4_deadline_linked_to_correct_cycle(active_rows, cycle_rows),
        check_5_no_test_fixtures_in_feed(),
        check_6_excluded_cycles_dont_leak(cycle_rows),
    ]

    print(f"Release gate run — {len(active_rows)} ACTIVE_CANDIDATE rows checked against {len(cycle_rows)} sale-cycle registry rows\n")
    overall_pass = True
    results = []
    for i, (desc, failures, details) in enumerate(checks, 1):
        status = "PASS" if not failures else "FAIL"
        if failures:
            overall_pass = False
        print(f"[{status}] Check {i}: {desc}  ({len(failures)} failure(s))")
        for d in details:
            print(f"         - {d}")
        results.append({"check": i, "description": desc, "status": status, "failure_count": len(failures), "details": details})

    print(f"\nOverall: {'PASS - safe to release' if overall_pass else 'FAIL - DO NOT RELEASE until resolved'}")

    out = ROOT / "release" / "release_gate_result.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"overall_pass": overall_pass, "checks": results, "active_candidate_count": len(active_rows)}, indent=2), encoding="utf-8")
    print(f"\nSaved gate result to {out}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
