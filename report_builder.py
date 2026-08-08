"""
report_builder.py — Template-Driven Deliverable & Dashboard Report Generator.

Fills standardized templates with verified data and predictive scores, placing final
deliverables into `output/dashboard/` and updating `dashboard_feed.json`.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lead_status import LeadStatus, evaluate_lead
from predictive_scorer import score_excess_proceeds, score_property_intelligence
from signal_priority import get_auction_window_display, get_signal

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DASHBOARD = ROOT / "output" / "dashboard"
FEED_FILE = OUTPUT_DASHBOARD / "dashboard_feed.json"


def build_excess_proceeds_report(claim_data: dict[str, Any], county: str) -> Path:
    """Generate an Excess Proceeds & Heir Claim report from template."""
    scores = score_excess_proceeds(claim_data)

    template_file = TEMPLATES_DIR / "excess_proceeds_claim.md"
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")

    content = template_file.read_text(encoding="utf-8")

    apn_dash = claim_data.get("apn_dash") or claim_data.get("apn") or ""
    county_name = county.replace("_", " ").title()

    # An amount of exactly None means "genuinely not disclosed by the county"
    # (e.g. Shasta, which only reveals the figure to an approved claimant
    # after filing) — this must never render as "$0.00", which would falsely
    # imply the county confirmed there's nothing to claim.
    if claim_data.get("excess_proceeds") is None:
        excess_amount_display = "UNDISCLOSED BY COUNTY (see verification notes)"
    else:
        excess_amount_display = f"${scores['excess_amount_clean']:,.2f}"

    # Run every record through the lead-status state machine before it can
    # be presented as anything resembling "active" — built directly from
    # the Nevada incident (2026-08-08): a record that's source-verified
    # but has an expired deadline must never reach ACTIVE_CANDIDATE, full
    # stop, no code path around it. See lead_status.py.
    # Default: any non-empty source_file/source_url description counts as
    # verified (true for every county with a real preserved, hashed
    # artifact). An enrichment script can override this explicitly via
    # source_artifact_verified=False when it knows the underlying artifact
    # itself was never saved/hashed (e.g. Sonoma's scraped results page) -
    # a descriptive citation string is not the same as a verified artifact.
    default_source_verified = bool(claim_data.get("source_file") or claim_data.get("source_url"))
    lead_eval = evaluate_lead(
        source_verified=claim_data.get("source_artifact_verified", default_source_verified),
        deadline_raw=claim_data.get("claim_deadline"),
        run_date=datetime.now().date(),
        amount_disclosed=claim_data.get("excess_proceeds") is not None,
        cycle_expired=bool(claim_data.get("sale_cycle_expired")),
    )
    LEAD_STATUS_STATEMENTS = {
        LeadStatus.ACTIVE_CANDIDATE: (
            "Potential excess-proceeds opportunity; public county source; deadline verified; "
            "claimant eligibility requires review."
        ),
        LeadStatus.EXPIRED: (
            f"EXPIRED — {lead_eval.reason}. Do not present as active, claimable, open, or actionable."
        ),
        LeadStatus.DEADLINE_UNVERIFIABLE: (
            f"DEADLINE UNVERIFIABLE — {lead_eval.reason}. Requires human review before any status can be assigned."
        ),
        LeadStatus.EXTRACTED: (
            f"SOURCE UNVERIFIED — {lead_eval.reason}."
        ),
    }
    lead_status_statement = LEAD_STATUS_STATEMENTS.get(lead_eval.status, lead_eval.reason)

    replacements = {
        "{{county_name}}": county_name,
        "{{generated_date}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{{apn_dash}}": apn_dash,
        "{{lead_status}}": lead_eval.status.value.upper(),
        "{{lead_status_statement}}": lead_status_statement,
        "{{excess_amount}}": excess_amount_display,
        "{{owner_name}}": claim_data.get("owner") or claim_data.get("owner_name") or "UNKNOWN",
        "{{former_owner}}": claim_data.get("former_owner") or "N/A",
        "{{claim_deadline}}": claim_data.get("claim_deadline") or "N/A",
        "{{urgency_status}}": scores["urgency_status"],
        "{{recoverability_score}}": str(scores["recoverability_score"]),
        "{{heir_locatability_tier}}": scores["heir_locatability_tier"],
        "{{deed_date}}": claim_data.get("deed_date") or "N/A",
        "{{deed_status}}": claim_data.get("deed_status") or "N/A",
        "{{auction_winner}}": claim_data.get("auction_winner") or "N/A",
        "{{situs}}": claim_data.get("situs") or "No Situs Address",
        "{{doc_number}}": claim_data.get("current_doc_number") or claim_data.get("doc_number") or "N/A",
        "{{assessed_value}}": f"{float(claim_data.get('values') or 0):,.2f}" if claim_data.get("values") else "N/A",
        "{{verification_status}}": claim_data.get("verification") or "UNVERIFIED — SOURCE NOT CONFIRMED",
        "{{source_url_or_file}}": claim_data.get("source_file") or claim_data.get("source_url") or "UNKNOWN — SOURCE NOT RECORDED",
    }

    for k, v in replacements.items():
        content = content.replace(k, str(v))

    OUTPUT_DASHBOARD.mkdir(parents=True, exist_ok=True)
    clean_apn = apn_dash.replace("-", "")
    out_file = OUTPUT_DASHBOARD / f"{county.lower()}_{clean_apn}_excess_claim.md"
    out_file.write_text(content, encoding="utf-8")

    # Update dashboard feed
    _update_dashboard_feed({
        "type": "EXCESS_PROCEEDS",
        "county": county_name,
        "apn": apn_dash,
        "owner": replacements["{{owner_name}}"],
        "excess_amount": scores["excess_amount_clean"],
        "recoverability_score": scores["recoverability_score"],
        "claim_deadline": replacements["{{claim_deadline}}"],
        "urgency_status": scores["urgency_status"],
        "lead_status": lead_eval.status.value,
        "report_path": str(out_file.resolve()),
        "timestamp": datetime.now().isoformat(),
    })

    print(f"[report_builder] Saved Excess Proceeds report to {out_file.resolve()}", file=sys.stderr)
    return out_file


def build_property_intelligence_dossier(parcel_data: dict[str, Any], county: str) -> Path:
    """Generate a Pre-Auction Property Intelligence Dossier from template."""
    scores = score_property_intelligence(parcel_data)

    template_file = TEMPLATES_DIR / "property_intelligence_dossier.md"
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")

    content = template_file.read_text(encoding="utf-8")

    apn_dash = parcel_data.get("apn_dash") or parcel_data.get("apn") or ""
    county_name = county.replace("_", " ").title()

    # Identifier integrity (DOSSIER_QA finding, 2026-08-08): a raw source
    # identifier must never be silently displayed as an "APN" unless it has
    # actually been independently verified as the assessor's own parcel
    # number. Kern's source data conflates an ATN (Assessment/Tax Number,
    # 5-segment format e.g. "017-490-06-00-3") with the assessor's real,
    # shorter parcel number ("017-490-06") - see property_model.py. A
    # caller can pass these explicitly (Kern's enrichment script does);
    # otherwise, default to treating apn_dash as the identifier at face
    # value, honestly labeled as not independently re-verified this run
    # rather than silently upgraded to "confirmed."
    source_identifier = parcel_data.get("source_identifier") or apn_dash
    source_identifier_type = parcel_data.get("source_identifier_type") or "APN (from source list)"
    assessor_apn = parcel_data.get("assessor_apn")
    assessor_apn_verification_status = parcel_data.get("assessor_apn_verification_status")
    if assessor_apn is None:
        assessor_apn = apn_dash
        assessor_apn_verification_status = assessor_apn_verification_status or (
            "NOT_VERIFIED — matches expected assessor APN format from the source list; "
            "not independently re-confirmed by reading the assessor's own displayed APN field this run"
        )

    # Use the scorer's own assessed_val_clean — it already checks every known
    # field-name variant (net_taxable_value, net_assessed_value, values,
    # assessed_total, TOTAL_ASSESSED_VALUE, ...). Recomputing from a narrower
    # key subset here previously caused real assessed values to silently read
    # as $0 whenever the source used a different field name than this function
    # happened to check.
    assessed = scores["assessed_val_clean"] or 0.0
    min_bid = scores["min_bid_clean"] or (assessed * 0.25 if assessed else 0.0)

    owner_str = parcel_data.get("owner") or parcel_data.get("owner_name") or "UNKNOWN"
    is_entity = any(kw in owner_str.upper() for kw in ["LLC", "INC", "CORP", "TRUST", "HOLDINGS", "GROUP"])
    entity_type = "Corporate Entity / Trust" if is_entity else "Individual"

    # Completeness gate: a record missing owner and/or assessed value cannot be
    # asserted as a verified, tiered opportunity — no matter what the raw score
    # formula computed. Downstream consumers must see "unverified", not a fake tier.
    missing_fields = []
    if owner_str == "UNKNOWN":
        missing_fields.append("owner")
    if not (assessed and assessed > 0):
        missing_fields.append("assessed_value")
    if not (parcel_data.get("current_doc_number") or parcel_data.get("doc_number")):
        missing_fields.append("doc_number")

    if "owner" in missing_fields or "assessed_value" in missing_fields:
        scores["opportunity_tier"] = "UNVERIFIED (Insufficient Source Data)"
        scores["equity_signal"] = "UNKNOWN"
        verification_status_val = "UNVERIFIED — SOURCE DATA INCOMPLETE"
    else:
        verification_status_val = parcel_data.get("verification_status") or "PARTIALLY VERIFIED — SEE DATA GAPS"

    # Secondary gaps: don't affect the tier/gate above (those 3 fields are the
    # ones that make a record untrustworthy as an "opportunity"), but a dossier
    # missing e.g. situs/doc_count/transfer_tax genuinely has gaps and must not
    # silently say "None found" just because the 3 gating fields are present.
    secondary_gap_checks = {
        "situs": parcel_data.get("situs"),
        "doc_count": parcel_data.get("recorder_doc_count") or parcel_data.get("doc_count"),
        "transfer_tax": parcel_data.get("transfer_tax"),
        "acreage": parcel_data.get("acreage") or parcel_data.get("lot_size"),
        "buyer_match": parcel_data.get("matched_buyers_count"),
    }
    secondary_gaps = [k for k, v in secondary_gap_checks.items() if not v]
    all_gaps = missing_fields + secondary_gaps

    if parcel_data.get("data_gaps"):
        data_gaps_val = parcel_data["data_gaps"]
    elif all_gaps:
        data_gaps_val = "Missing: " + ", ".join(all_gaps)
    else:
        data_gaps_val = "None found"

    signal = get_signal(county)

    # Auction-confirmation wording (DOSSIER_QA finding, 2026-08-08): the
    # county-level auction CALENDAR (signal_priority.AUCTION_CALENDAR) only
    # confirms a county-wide auction DATE, not that any specific parcel is
    # actually on that auction's real, current, published parcel list.
    # Kern's dossiers were stating "GOING TO AUCTION in N days" for every
    # parcel from a historical snapshot, before the real Sept 2026 list was
    # even published - overclaiming parcel-specific confirmation. Only
    # display the auction-imminent wording when the caller explicitly
    # confirms this exact parcel was matched against a real, current,
    # official parcel-level auction list.
    if signal["signal_type"] == "PRE_AUCTION_PRIORITY_1" and not parcel_data.get("auction_list_membership_verified"):
        priority_signal_display = (
            "Tax-default / Power-to-Sell public-record indicator; parcel-specific auction status not verified "
            f"(county auction window confirmed {get_auction_window_display(county)}, but this parcel's presence "
            "on the current, official parcel-level auction list has not been independently confirmed)"
        )
    else:
        priority_signal_display = signal["priority_label"]

    replacements = {
        "{{county_name}}": county_name,
        "{{generated_date}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{{apn_dash}}": apn_dash,
        "{{source_identifier}}": source_identifier,
        "{{source_identifier_type}}": source_identifier_type,
        "{{assessor_apn}}": assessor_apn,
        "{{assessor_apn_verification_status}}": assessor_apn_verification_status or "NOT_VERIFIED",
        "{{priority_signal}}": priority_signal_display,
        "{{opportunity_tier}}": scores["opportunity_tier"],
        "{{seller_intent_score}}": str(scores["seller_intent_score"]),
        "{{equity_ratio_pct}}": f"{scores['equity_ratio'] * 100:.1f}",
        "{{equity_signal}}": scores["equity_signal"],
        "{{min_bid}}": f"{min_bid:,.2f}",
        "{{assessed_value}}": f"{assessed:,.2f}",
        "{{predicted_auction_window}}": parcel_data.get("predicted_auction_window") or get_auction_window_display(county),
        "{{owner_name}}": owner_str,
        "{{entity_type}}": entity_type,
        "{{is_out_of_state_owner}}": "Yes" if scores["is_out_of_state_owner"] else "No",
        "{{situs}}": parcel_data.get("situs") or "No Situs Address",
        "{{use_code}}": parcel_data.get("use") or parcel_data.get("use_code") or "Standard Real Property",
        "{{lot_size}}": parcel_data.get("acreage") or parcel_data.get("lot_size") or "N/A",
        "{{tax_status}}": parcel_data.get("tax_status") or "N/A — not confirmed in source data",
        "{{tax_default_year}}": parcel_data.get("tax_default_year") or "N/A",
        "{{doc_number}}": parcel_data.get("current_doc_number") or parcel_data.get("doc_number") or "N/A",
        "{{deed_date}}": parcel_data.get("deed_date") or "N/A",
        "{{transfer_tax}}": parcel_data.get("transfer_tax") or "N/A",
        "{{transfer_price}}": parcel_data.get("transfer_price") or "N/A",
        "{{doc_count}}": parcel_data.get("recorder_doc_count") or parcel_data.get("doc_count") or "N/A",
        "{{notice_status}}": "Recorded Notice of Power to Sell Present" if parcel_data.get("notice_of_default_present") else "Standard Default Notice",
        "{{matched_buyers_count}}": (
            f"{parcel_data['matched_buyers_count']} active repeat buyers tracked in {county_name}"
            if parcel_data.get("matched_buyers_count")
            else f"N/A — buyer match not run for {county_name}"
        ),
        "{{top_matched_buyer}}": parcel_data.get("top_matched_buyer") or "No Verified Buyer Match",
        "{{top_buyer_score}}": parcel_data.get("top_buyer_score") or "N/A",
        "{{source_url_or_file}}": parcel_data.get("source_url") or parcel_data.get("source_file") or "UNKNOWN — SOURCE NOT RECORDED",
        "{{verification_status}}": verification_status_val,
        "{{data_gaps}}": data_gaps_val,
    }

    for k, v in replacements.items():
        content = content.replace(k, str(v))

    OUTPUT_DASHBOARD.mkdir(parents=True, exist_ok=True)
    clean_apn = apn_dash.replace("-", "")
    out_file = OUTPUT_DASHBOARD / f"{county.lower()}_{clean_apn}_prop_intel_dossier.md"
    out_file.write_text(content, encoding="utf-8")

    # Update dashboard feed
    _update_dashboard_feed({
        "type": "PROPERTY_INTELLIGENCE",
        "county": county_name,
        "apn": apn_dash,
        "owner": replacements["{{owner_name}}"],
        "opportunity_tier": scores["opportunity_tier"],
        "seller_intent_score": scores["seller_intent_score"],
        "equity_ratio_pct": replacements["{{equity_ratio_pct}}"],
        "signal_type": signal["signal_type"],
        "priority_signal": signal["priority_label"],
        "days_until_auction": signal["days_until_auction"],
        "report_path": str(out_file.resolve()),
        "timestamp": datetime.now().isoformat(),
    })

    print(f"[report_builder] Saved Property Intelligence Dossier to {out_file.resolve()}", file=sys.stderr)
    return out_file


def _update_dashboard_feed(entry: dict[str, Any]) -> None:
    """Maintain rolling dashboard JSON feed of all generated reports."""
    feed = []
    if FEED_FILE.exists():
        try:
            feed = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        except Exception:
            feed = []

    # Insert latest at beginning
    feed.insert(0, entry)
    feed = feed[:200]  # keep latest 200

    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEED_FILE.write_text(json.dumps(feed, indent=2), encoding="utf-8")


def main() -> int:
    # Test generation for Casey parcel
    sample_casey = {
        "apn_dash": "305-073-053-000",
        "owner": "CASEY B A",
        "former_owner": "CASEY B A",
        "excess_proceeds": "11481.75",
        "claim_deadline": "2027-06-18",
        "deed_status": "deed_confirmed_by_block_match",
        "auction_winner": "LUC KEVIN",
        "situs": "No Situs Address",
        "current_doc_number": "2026-007963",
        "deed_date": "06/18/2026",
    }
    rf = build_excess_proceeds_report(sample_casey, "humboldt")
    print(f"Generated report: {rf}")
    return 0


if __name__ == "__main__":
    main()
