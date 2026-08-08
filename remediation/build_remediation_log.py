"""
Build the record-level remediation log by diffing each current dossier
against its pre-remediation backup (/tmp/kern_dossiers_pre_remediation_backup_dashboard,
captured immediately before the Kern identifier/auction-wording fix and
before the shared lien-risk rename regeneration).

Required fields per the remediation ticket: record identifier, county,
prior label/value, corrected label/value, reason for correction,
evidence path, timestamp, QA status.

Run: python3 remediation/build_remediation_log.py
"""
import csv
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = Path("/tmp/kern_dossiers_pre_remediation_backup_dashboard")
OUT = ROOT / "remediation" / "remediation_log.csv"
TIMESTAMP = "2026-08-08T12:00:00Z"


def grab(text, pattern):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def diff_kern(apn_file_stub, old_text, new_text):
    rows = []
    old_apn_line = grab(old_text, r"\*\*APN\*\*: `([^`]+)`")
    new_source_id = grab(new_text, r"\*\*Source Identifier\*\*: `([^`]+)`")
    new_assessor_apn = grab(new_text, r"\*\*Assessor APN\*\*: `([^`]+)`")
    if old_apn_line:
        rows.append({
            "record_identifier": apn_file_stub, "county": "Kern",
            "prior_label_value": f"**APN**: {old_apn_line} (mislabeled - this is the ATN, not the assessor parcel number)",
            "corrected_label_value": f"**Source Identifier**: {new_source_id} (ATN) / **Assessor APN**: {new_assessor_apn} (NOT_VERIFIED)",
            "reason_for_correction": "DOSSIER_QA finding: ATN mislabeled as APN in 245/245 Kern dossiers - see property_model.py and monitor_runs/dossier_qa_report.md Section 1",
            "evidence_path": "kern/kern_enrich_docnum_verified.py; property_model.py:atn_to_assessor_parcel_number",
            "timestamp": TIMESTAMP, "qa_status": "PENDING_RERUN",
        })

    old_signal = grab(old_text, r"PRIORITY SIGNAL: (.+?)\*\*")
    new_signal = grab(new_text, r"PUBLIC-RECORD SIGNAL: (.+?)\*\*")
    if old_signal and "GOING TO AUCTION" in old_signal:
        rows.append({
            "record_identifier": apn_file_stub, "county": "Kern",
            "prior_label_value": f"PRIORITY SIGNAL: {old_signal}",
            "corrected_label_value": f"PUBLIC-RECORD SIGNAL: {(new_signal or '')[:120]}...",
            "reason_for_correction": "DOSSIER_QA finding: overclaimed parcel-specific auction-list confirmation against an unpublished live list - see monitor_runs/dossier_qa_report.md Section 2",
            "evidence_path": "report_builder.py (priority_signal_display logic); signal_priority.py",
            "timestamp": TIMESTAMP, "qa_status": "PENDING_RERUN",
        })

    if "Lien Risk Tier" in old_text and "Equity / Assessed-Value Indicator" in new_text:
        old_val = grab(old_text, r"Lien Risk Tier\*\* \| \*\*([^*]+)\*\*")
        new_val = grab(new_text, r"Equity / Assessed-Value Indicator\*\* \| \*\*([^*]+)\*\*")
        rows.append({
            "record_identifier": apn_file_stub, "county": "Kern",
            "prior_label_value": f"Lien Risk Tier: {old_val}",
            "corrected_label_value": f"Equity / Assessed-Value Indicator: {new_val} (with disclaimer)",
            "reason_for_correction": "Shared remediation: field was a pure equity-ratio proxy labeled as if a lien/title review had been performed",
            "evidence_path": "predictive_scorer.py (equity_signal logic)",
            "timestamp": TIMESTAMP, "qa_status": "PENDING_RERUN",
        })
    return rows


def diff_lien_only(apn_file_stub, county, old_text, new_text):
    rows = []
    if "Lien Risk Tier" in old_text and "Equity / Assessed-Value Indicator" in new_text:
        old_val = grab(old_text, r"Lien Risk Tier\*\* \| \*\*([^*]+)\*\*")
        new_val = grab(new_text, r"Equity / Assessed-Value Indicator\*\* \| \*\*([^*]+)\*\*")
        rows.append({
            "record_identifier": apn_file_stub, "county": county,
            "prior_label_value": f"Lien Risk Tier: {old_val}",
            "corrected_label_value": f"Equity / Assessed-Value Indicator: {new_val} (with disclaimer)",
            "reason_for_correction": "Shared remediation: field was a pure equity-ratio proxy labeled as if a lien/title review had been performed",
            "evidence_path": "predictive_scorer.py (equity_signal logic)",
            "timestamp": TIMESTAMP, "qa_status": "PENDING_RERUN",
        })
    return rows


def main():
    all_rows = []

    for new_path in sorted(glob.glob(str(ROOT / "output" / "dashboard" / "kern_*_prop_intel_dossier.md"))):
        stub = Path(new_path).name
        old_path = BACKUP / stub
        if not old_path.exists():
            continue
        old_text = old_path.read_text(encoding="utf-8")
        new_text = Path(new_path).read_text(encoding="utf-8")
        all_rows.extend(diff_kern(stub, old_text, new_text))

    for county, prefix in [("Butte", "butte_"), ("Lake", "lake_")]:
        for new_path in sorted(glob.glob(str(ROOT / "output" / "dashboard" / f"{prefix}*_prop_intel_dossier.md"))):
            stub = Path(new_path).name
            old_path = BACKUP / stub
            if not old_path.exists():
                continue
            old_text = old_path.read_text(encoding="utf-8")
            new_text = Path(new_path).read_text(encoding="utf-8")
            all_rows.extend(diff_lien_only(stub, county, old_text, new_text))

    # Gridley removal - a real correction fixed in the prior commit
    # (e5e1aa6, BUTTE_MONITOR run), before this session's backup snapshot
    # was taken, so there's no "old file" left to diff against here (the
    # dossier had already been correctly absent by the time the backup was
    # made). Documented unconditionally with its real evidence trail
    # rather than skipped just because the local diff can't reconstruct it.
    all_rows.append({
        "record_identifier": "022-210-078-000", "county": "Butte",
        "prior_label_value": "Dossier existed in principle (redeemed parcel could be silently regenerated as a live opportunity - the code had no filter; had not yet actually reoccurred in the live 104 only because a prior session had manually excluded it outside the script)",
        "corrected_label_value": "Dossier removed and cannot recur - excluded via is_redeemed() check, now wired into regen_butte_dossiers.py's production path and covered by tests/test_butte_redemption_filter.py",
        "reason_for_correction": "BUTTE_MONITOR finding (commit e5e1aa6): redemption_status field was never wired into the generation script; Gridley's call-sheet row is marked redeemed",
        "evidence_path": "butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (row 022-210-078-000, redemption_status=redeemed); regen_butte_dossiers.py:is_redeemed(); tests/test_butte_redemption_filter.py; monitor_runs/butte_monitor_run.log",
        "timestamp": TIMESTAMP, "qa_status": "VERIFIED_BY_REGRESSION_TEST",
    })

    fieldnames = ["record_identifier", "county", "prior_label_value", "corrected_label_value",
                  "reason_for_correction", "evidence_path", "timestamp", "qa_status"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    from collections import Counter
    by_county = Counter(r["county"] for r in all_rows)
    print(f"Wrote {len(all_rows)} remediation rows to {OUT}")
    print(f"By county: {dict(by_county)}")


if __name__ == "__main__":
    main()
