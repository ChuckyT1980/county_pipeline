"""
Generates a 1-page PDF cover summary for the Butte auction call sheet.

Client-facing deliverable: methodology, headline stats, top-10 preview
table, and a disclaimer. Uses fpdf2 for text layout.
"""
import os
import sys
from datetime import datetime

import pandas as pd
from fpdf import FPDF

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

CALL_SHEET = os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
OUTPUT_PDF = os.path.join(os.path.dirname(__file__), "butte_auction_call_sheet_cover.pdf")


def _money_to_float(s):
    if pd.isna(s):
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt_money(v: float) -> str:
    return f"${v:,.0f}"


def build(csv_path: str = CALL_SHEET, output: str = OUTPUT_PDF) -> str:
    df = pd.read_csv(csv_path, dtype=str)
    df["bal_num"] = df["v_total_balance"].apply(_money_to_float)
    df["score_num"] = pd.to_numeric(df["priority_score"], errors="coerce")

    total_leads = len(df)
    total_balance = df["bal_num"].sum()
    has_owner = df["verified_current_owner_name"].notna() & (df["verified_current_owner_name"].astype(str).str.strip().str.lower() != "nan")
    has_phone = df["phone_number"].notna() & (df["phone_number"].astype(str).str.strip() != "") & (df["phone_number"].astype(str).str.strip().str.lower() != "nan")
    has_mailing = df["mailing_address"].notna() & (df["mailing_address"].astype(str).str.strip() != "") & (df["mailing_address"].astype(str).str.strip().str.lower() != "nan")
    out_of_state = (df["out_of_state"] == "Y").sum() if "out_of_state" in df.columns else 0

    # Verification substrate stats (Phase 0)
    if "verification_score" in df.columns:
        vs = df["verification_score"]
        verified_mask = vs.notna() & (vs.astype(str).str.strip() != "") & (vs.astype(str).str.strip().str.lower() != "nan")
        verified_count = int(verified_mask.sum())
        try:
            avg_completeness = pd.to_numeric(df.loc[verified_mask, "verification_score"], errors="coerce").mean()
        except Exception:
            avg_completeness = None
    else:
        verified_count = 0
        avg_completeness = None

    # Portfolio detection (Phase 3)
    portfolio_series = pd.to_numeric(df.get("portfolio_apn_count"), errors="coerce") if "portfolio_apn_count" in df.columns else None
    portfolio_flagged = int((portfolio_series >= 2).sum()) if portfolio_series is not None else 0

    # Environmental (Phase 1)
    if "fire_hazard_zone" in df.columns:
        fire_very_high = int((df["fire_hazard_zone"] == "Very High").sum())
        fire_high = int((df["fire_hazard_zone"] == "High").sum())
        fire_moderate = int((df["fire_hazard_zone"] == "Moderate").sum())
        fire_zoned_total = fire_very_high + fire_high + fire_moderate
    else:
        fire_very_high = fire_high = fire_moderate = fire_zoned_total = 0

    if "flood_zone" in df.columns:
        flood_high_risk = int(df["flood_zone"].isin(["A", "AE", "VE", "V", "AH", "AO"]).sum())
    else:
        flood_high_risk = 0

    # Ownership (Phase 4)
    if "ownership_confidence" in df.columns:
        oc_num = pd.to_numeric(df["ownership_confidence"], errors="coerce")
        high_conf_ownership = int((oc_num >= 0.70).sum())
        low_conf_ownership = int((oc_num < 0.50).sum())
    else:
        high_conf_ownership = low_conf_ownership = 0

    # Consistency (Phase 2)
    from verification.db import connect as _vconnect
    try:
        _conn = _vconnect()
        consistency_row = _conn.execute(
            "SELECT COUNT(*) AS n FROM verification_flags WHERE layer='consistency' AND severity IN ('warn','error')"
        ).fetchone()
        consistency_flags_total = consistency_row["n"] if consistency_row else 0

        # Graph size — the depth of the recorder network we crawled
        graph_row = _conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='doc' AND county='butte') AS docs,
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='person') AS persons,
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='entity') AS entities
            """
        ).fetchone()
        graph_docs = graph_row["docs"] if graph_row else 0
        graph_actors = (graph_row["persons"] + graph_row["entities"]) if graph_row else 0
        _conn.close()
    except Exception:
        consistency_flags_total = 0
        graph_docs = 0
        graph_actors = 0

    # Distress signals (Phase 3+)
    if "distress_signal_score" in df.columns:
        ds_num = pd.to_numeric(df["distress_signal_score"], errors="coerce").fillna(0)
        high_distress = int((ds_num >= 30).sum())
        with_signals = int((ds_num > 0).sum())
    else:
        high_distress = with_signals = 0

    entity_counts = df["entity_type"].value_counts(dropna=True).to_dict()

    top10 = df.sort_values("score_num", ascending=False).head(10)

    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "Butte County Tax Auction  Call Sheet", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Aug 7-10, 2026 Auction  Prepared {datetime.now():%B %d, %Y}", ln=True)
    pdf.ln(2)

    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "Methodology", ln=True)
    pdf.set_font("Helvetica", "", 9)
    methodology = (
        "Every parcel scheduled for the Butte County Aug 7-10 tax-defaulted auction was pulled "
        "from the county tax collector's site, verified for active delinquency, cross-referenced "
        "against the county recorder's chain of title, and enriched with the assessor's mailing "
        "address of record. Each lead is priority-scored 50-100 on a log-scaled function of "
        "defaulted balance (linear 50-80 up to $50k, log 80-100 from $50k to $2.5M+). "
        "Out-of-state absentee owners are flagged separately."
    )
    pdf.multi_cell(0, 4, methodology)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "Summary", ln=True)
    pdf.set_font("Helvetica", "", 9)
    lines = [
        f"Total leads on auction list: {total_leads}",
        f"Total defaulted balance across all parcels: {_fmt_money(total_balance)}",
        f"Leads with owner name identified: {has_owner.sum()} of {total_leads} ({has_owner.sum()*100//total_leads}%)",
        f"Leads with mailing address (direct-mail ready): {has_mailing.sum()} of {total_leads} ({has_mailing.sum()*100//total_leads}%)",
        f"Leads with phone number: {has_phone.sum()} of {total_leads} ({has_phone.sum()*100//total_leads}%)",
        f"Out-of-state absentee owners flagged: {out_of_state} of {total_leads}",
    ]
    for line in lines:
        pdf.cell(0, 4.5, "  - " + line, ln=True)

    if entity_counts:
        breakdown = "  - Owner type breakdown: " + ", ".join(
            f"{v} {k.lower()}" for k, v in sorted(entity_counts.items(), key=lambda x: -x[1])
        )
        pdf.cell(0, 4.5, breakdown, ln=True)
    pdf.ln(2)

    # Verification section (Phases 0-4)
    if verified_count > 0:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 5, "Verification & Intelligence", ln=True)
        pdf.set_font("Helvetica", "", 9)
        avg_str = f"{avg_completeness:.0f}%" if avg_completeness is not None else "n/a"
        pdf.cell(0, 4.5, f"  - Every field carries a source + confidence stamp (5-layer verification stack)", ln=True)
        pdf.cell(0, 4.5, f"  - Provenance recorded for {verified_count} of {total_leads} leads; data completeness {avg_str}", ln=True)
        if portfolio_flagged > 0:
            pdf.cell(0, 4.5, f"  - Portfolio owners detected (>=2 auction parcels each): {portfolio_flagged} of {total_leads}", ln=True)
        if fire_zoned_total > 0:
            pdf.cell(0, 4.5, f"  - Fire hazard flagged: {fire_very_high} Very High, {fire_high} High, {fire_moderate} Moderate (CalFire FHSZ)", ln=True)
        if flood_high_risk > 0:
            pdf.cell(0, 4.5, f"  - FEMA high-risk flood zones: {flood_high_risk} (Zone A/AE/V/VE)", ln=True)
        if high_conf_ownership > 0:
            pdf.cell(0, 4.5, f"  - High-confidence ownership (>=0.70): {high_conf_ownership}; low-confidence (<0.50): {low_conf_ownership}", ln=True)
        if consistency_flags_total > 0:
            pdf.cell(0, 4.5, f"  - Data-quality flags surfaced by consistency layer: {consistency_flags_total} (per-parcel column in CSV)", ln=True)
        if graph_docs > 0:
            pdf.cell(0, 4.5, f"  - Recorder graph: {graph_docs:,} historical documents, {graph_actors:,} people/entities cross-referenced", ln=True)
        if with_signals > 0:
            pdf.cell(0, 4.5, f"  - Historical distress signals per owner (NODs, liens, judgments, tax defaults): {with_signals} of {total_leads} leads carry positive signals; {high_distress} score >= 30", ln=True)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "Top 10 by Priority Score", ln=True)
    pdf.set_font("Helvetica", "B", 8)

    col_widths = [10, 15, 26, 45, 22, 78]
    headers = ["Rank", "Score", "APN", "Owner", "Balance", "Mailing Address"]
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 5, h, border=1, align="L")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for rank, (_, row) in enumerate(top10.iterrows(), start=1):
        owner = str(row.get("verified_current_owner_name", ""))
        if owner.lower() == "nan":
            owner = "(no name)"
        mail = str(row.get("mailing_address", ""))
        if mail.lower() == "nan":
            mail = ""
        pdf.cell(col_widths[0], 5, str(rank), border=1)
        pdf.cell(col_widths[1], 5, f"{float(row['score_num']):.1f}", border=1)
        pdf.cell(col_widths[2], 5, str(row["apn"]), border=1)
        pdf.cell(col_widths[3], 5, owner[:26], border=1)
        pdf.cell(col_widths[4], 5, _fmt_money(row["bal_num"]), border=1, align="R")
        pdf.cell(col_widths[5], 5, mail[:52], border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7)
    disclaimer = (
        "Disclaimer: Data pulled from Butte County Treasurer-Tax Collector and Butte County "
        "Recorder public records. Owner and mailing information reflects assessor records and "
        "may not represent current beneficial ownership. Priority scores are heuristic and are "
        "not investment advice. Verify all information independently before making offers or "
        "contacting owners. Skip-traced phone numbers are best-effort matches from public sources."
    )
    pdf.multi_cell(0, 3, disclaimer)

    pdf.output(output)
    return output


if __name__ == "__main__":
    out = build()
    size = os.path.getsize(out)
    print(f"Wrote {out} ({size} bytes)")
