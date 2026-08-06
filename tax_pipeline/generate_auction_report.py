#!/usr/bin/env python3
"""
Butte County Tax Auction Intelligence Report Generator
=======================================================
Produces 3 PDF tiers from the enriched auction dataset:

  Tier 1 — Snapshot Report  (Top 10 by score)  [$49]
  Tier 2 — Full Report      (Top 26, score 70+) [$149]
  Tier 3 — War Room Pack    (All 105)           [$297]

Run:  python generate_auction_report.py
Output: tax_pipeline/auction_reports/
"""

import fitz  # PyMuPDF 1.27+
import pandas as pd
import os, re
from datetime import datetime
from pathlib import Path

# ── Output directory ──────────────────────────────────────────────────────────
BASE    = Path(__file__).resolve().parent
OUT_DIR = BASE / "auction_reports"
OUT_DIR.mkdir(exist_ok=True)

CALL_SHEET_PATH = BASE.parent / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
TARGETS_PATH    = BASE / "butte_auction_targets_with_values.csv"

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY       = (0.106, 0.169, 0.290)
NAVY_LIGHT = (0.157, 0.224, 0.361)
GOLD       = (0.784, 0.659, 0.306)
SLATE      = (0.314, 0.357, 0.416)
LIGHT_BG   = (0.945, 0.950, 0.958)
WHITE      = (1.0,  1.0,  1.0)
DARK       = (0.133, 0.133, 0.133)
MED_GRAY   = (0.565, 0.592, 0.627)
GREEN_OK   = (0.098, 0.463, 0.271)
ORANGE_MED = (0.804, 0.373, 0.035)
RED_HIGH   = (0.722, 0.110, 0.110)
AMBER      = (0.820, 0.580, 0.000)

PAGE_W, PAGE_H = 612, 792
MARGIN = 36

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_R = fitz.Font("helv")          # Helvetica regular
FONT_B = fitz.Font("hebo")          # Helvetica Bold


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_dollar(val):
    try:
        v = float(str(val).replace("$", "").replace(",", "").strip())
        return f"${v:,.0f}"
    except Exception:
        return "N/A"

def clean(val, default="N/A"):
    s = str(val).strip()
    return s if s not in ("nan", "", "None") else default

def score_color(score):
    try:
        s = float(score)
        if s >= 80: return RED_HIGH
        if s >= 65: return ORANGE_MED
        return GREEN_OK
    except Exception:
        return MED_GRAY

def score_label(score):
    try:
        s = float(score)
        if s >= 80: return "PRIORITY"
        if s >= 65: return "STRONG"
        return "WATCH"
    except Exception:
        return "UNSCORED"

def tw_text(page, text, x, y, fontsize=10, color=DARK, bold=False):
    """Insert a single text string via TextWriter (PyMuPDF 1.27 compatible)."""
    tw = fitz.TextWriter(page.rect)
    font = FONT_B if bold else FONT_R
    tw.append((x, y), str(text), font=font, fontsize=fontsize)
    tw.write_text(page, color=color)

def fill_rect(page, x, y, w, h, fill, stroke=None, width=0.5):
    r = fitz.Rect(x, y, x + w, y + h)
    page.draw_rect(r, color=stroke, fill=fill, width=width)

def hline(page, x, y, w, color=GOLD, width=1):
    page.draw_line(fitz.Point(x, y), fitz.Point(x + w, y), color=color, width=width)


# ── Data loading & merge ──────────────────────────────────────────────────────

def load_data():
    cs = pd.read_csv(CALL_SHEET_PATH)
    tv = pd.read_csv(TARGETS_PATH)

    def norm(s):
        return re.sub(r"[^0-9]", "", str(s))

    cs["_key"] = cs["apn"].apply(norm)
    tv["_key"] = tv["apn_dash"].apply(norm)
    df = cs.merge(tv, on="_key", how="left", suffixes=("_cs", "_tv"))

    df["balance_num"] = (
        df["v_total_balance"].astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .pipe(pd.to_numeric, errors="coerce").fillna(0)
    )
    df["nav_num"]     = pd.to_numeric(df["net_assessed_value"], errors="coerce").fillna(0)
    df["min_bid_num"] = pd.to_numeric(df["min_bid"], errors="coerce").fillna(0)
    df["max_bid_num"] = pd.to_numeric(df["max_bid_threshold"], errors="coerce").fillna(0)
    df["score_num"]   = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0)

    df["flag_no_addr"]  = df["address"].astype(str).str.contains(
        r"No Address|^nan$|^$", case=False, regex=True, na=True)
    df["flag_no_owner"] = df["verified_current_owner_name"].isna()
    df["flag_no_nav"]   = df["nav_num"] == 0

    return df.sort_values("score_num", ascending=False).reset_index(drop=True)


# ── Cover page ────────────────────────────────────────────────────────────────

def draw_cover(doc, label, subtitle, n, total_bal, auction_date, ts):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    fill_rect(page, 0, 0, PAGE_W, 224, fill=NAVY)
    fill_rect(page, 0, 224, PAGE_W, 5, fill=GOLD)

    # Badge
    fill_rect(page, MARGIN, 36, 190, 22, fill=GOLD)
    tw_text(page, "TAX AUCTION INTELLIGENCE  |  BUTTE COUNTY", MARGIN + 8, 52,
            fontsize=8, color=NAVY, bold=True)

    # Auction callout box (top-right)
    fill_rect(page, PAGE_W - 195, 28, 168, 68, fill=NAVY_LIGHT)
    tw_text(page, "AUCTION DATES", PAGE_W - 183, 48, fontsize=7.5, color=GOLD, bold=True)
    tw_text(page, auction_date, PAGE_W - 183, 70, fontsize=13, color=WHITE, bold=True)
    tw_text(page, "Bid4Assets Online Auction", PAGE_W - 183, 86, fontsize=7.5, color=MED_GRAY)

    tw_text(page, "BUTTE COUNTY", MARGIN, 108, fontsize=26, color=WHITE, bold=True)
    tw_text(page, label, MARGIN, 144, fontsize=20, color=GOLD, bold=True)
    tw_text(page, subtitle, MARGIN, 172, fontsize=10, color=(0.78, 0.84, 0.92))

    # Metrics strip
    metrics = [
        ("PROPERTIES", str(n),              "in this report"),
        ("TOTAL TAX OWED", fmt_dollar(total_bal), "delinquent balance"),
        ("DATA SOURCE", "Assessor + Recorder", "Live county records"),
        ("GENERATED", ts, "Pacific Time"),
    ]
    y_m = 242
    col = (PAGE_W - 2 * MARGIN) / 4
    for i, (lbl, val, sub) in enumerate(metrics):
        x = MARGIN + i * col
        fill_rect(page, x + 3, y_m, col - 6, 68, fill=LIGHT_BG)
        tw_text(page, lbl, x + 10, y_m + 16, fontsize=7, color=SLATE, bold=True)
        tw_text(page, val[:18], x + 10, y_m + 38, fontsize=12, color=NAVY, bold=True)
        tw_text(page, sub, x + 10, y_m + 53, fontsize=7, color=MED_GRAY)

    # Disclaimer
    y_d = 330
    fill_rect(page, MARGIN, y_d, PAGE_W - 2 * MARGIN, 60, fill=(1.0, 0.97, 0.90))
    fill_rect(page, MARGIN, y_d, 4, 60, fill=AMBER)
    tw_text(page, "DATA NOTICE", MARGIN + 12, y_d + 14, fontsize=7.5, color=AMBER, bold=True)
    notice = [
        "All data sourced from Butte County Assessor and Recorder public records (live, verified).",
        "Assessed values reflect county tax rolls — market value may differ significantly.",
        "Max bid thresholds are set at 70% of assessed value. Investor due diligence required.",
        "Properties flagged [!] have incomplete address or owner data from public records.",
    ]
    for j, line in enumerate(notice):
        tw_text(page, line, MARGIN + 12, y_d + 26 + j * 10, fontsize=7.5,
                color=(0.38, 0.28, 0.0))

    # What's inside
    y_i = 412
    tw_text(page, "WHAT'S IN THIS REPORT", MARGIN, y_i, fontsize=10, color=NAVY, bold=True)
    hline(page, MARGIN, y_i + 6, PAGE_W - 2 * MARGIN)
    bullets = [
        "Score 51-99.9 for every property — based on delinquency age, lien exposure, and equity",
        "Minimum bid vs. assessed value vs. max safe bid threshold (70% of assessed)",
        "Full lien profile: open mortgages, abstracts of judgment, notices of default",
        "Owner name + entity type (Individual / Trust / LLC / Corp) with vesting confidence %",
        "Score rationale — what specific factors drove each property's ranking",
        "Data quality flags where county public records are incomplete",
    ]
    for j, b in enumerate(bullets):
        tw_text(page, "•  " + b, MARGIN, y_i + 22 + j * 14, fontsize=9, color=DARK)

    # Footer
    fill_rect(page, 0, PAGE_H - 38, PAGE_W, 38, fill=NAVY)
    tw_text(page, "CONFIDENTIAL — FOR INVESTOR USE ONLY",
            MARGIN, PAGE_H - 20, fontsize=7.5, color=MED_GRAY)
    tw_text(page, "County Tax Auction Intelligence",
            PAGE_W - 210, PAGE_H - 20, fontsize=7.5, color=MED_GRAY)


# ── Summary table page ────────────────────────────────────────────────────────

def draw_summary(doc, df, title):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    fill_rect(page, 0, 0, PAGE_W, 50, fill=NAVY)
    fill_rect(page, 0, 50, PAGE_W, 4, fill=GOLD)
    tw_text(page, title, MARGIN, 32, fontsize=13, color=WHITE, bold=True)

    # Column spec: (header, width, x_offset_from_margin)
    COLS = [
        ("#",        24,   0),
        ("APN",      90,  24),
        ("Owner",   135, 114),
        ("Type",     46, 249),
        ("Min Bid",  52, 295),
        ("Assessed", 58, 347),
        ("Max Bid",  52, 405),
        ("Score",    44, 457),
    ]

    y_h = 72
    fill_rect(page, MARGIN, y_h - 2, PAGE_W - 2 * MARGIN, 17, fill=LIGHT_BG)
    for hdr, _, ox in COLS:
        tw_text(page, hdr, MARGIN + ox + 2, y_h + 10, fontsize=7.5, color=SLATE, bold=True)

    y = y_h + 21
    rh = 15
    for i, (_, row) in enumerate(df.iterrows()):
        if y + rh > PAGE_H - 42:
            tw_text(page, f"... {len(df)-i} more properties. See individual property cards.",
                    MARGIN, y + 10, fontsize=8, color=MED_GRAY)
            break
        bg = LIGHT_BG if i % 2 == 0 else WHITE
        fill_rect(page, MARGIN, y - 1, PAGE_W - 2 * MARGIN, rh, fill=bg)

        sc   = row.get("score_num", 0)
        vals = [
            str(i + 1),
            clean(row.get("apn", row.get("apn_dash", "")))[:15],
            clean(row.get("verified_current_owner_name", ""))[:22],
            clean(row.get("entity_type_cs", row.get("entity_type", "")))[:10],
            fmt_dollar(row.get("min_bid_num", 0)),
            fmt_dollar(row.get("nav_num", 0)) if row.get("nav_num", 0) > 0 else "N/A",
            fmt_dollar(row.get("max_bid_num", 0)) if row.get("max_bid_num", 0) > 0 else "N/A",
            str(round(float(sc), 1)),
        ]
        # Score badge
        fill_rect(page, MARGIN + 457, y - 1, 44, rh, fill=score_color(sc))

        for (_, _, ox), val in zip(COLS, vals):
            is_score = (ox == 457)
            tw_text(page, val, MARGIN + ox + 2, y + 10, fontsize=7.5,
                    color=WHITE if is_score else DARK)
        y += rh

    fill_rect(page, 0, PAGE_H - 38, PAGE_W, 38, fill=NAVY)
    tw_text(page, "Butte County Tax Auction  |  Aug 7–10, 2026  |  County Tax Auction Intelligence",
            MARGIN, PAGE_H - 16, fontsize=7.5, color=MED_GRAY)


# ── Property card ─────────────────────────────────────────────────────────────

def draw_card(doc, rank, row):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    score  = row.get("score_num", 0)
    sc_clr = score_color(score)
    sc_lbl = score_label(score)
    apn    = clean(row.get("apn", row.get("apn_dash", "")))
    owner  = clean(row.get("verified_current_owner_name", ""),
                   default="[Owner unresolved — skip trace required]")
    etype  = clean(row.get("entity_type_cs", row.get("entity_type", "")))

    # Header
    fill_rect(page, 0, 0, PAGE_W, 56, fill=NAVY)
    fill_rect(page, 0, 56, PAGE_W, 4, fill=GOLD)

    # Score badge
    fill_rect(page, PAGE_W - 88, 4, 76, 50, fill=sc_clr)
    tw_text(page, sc_lbl, PAGE_W - 80, 20, fontsize=7, color=WHITE, bold=True)
    tw_text(page, str(round(float(score), 1)), PAGE_W - 72, 47, fontsize=20, color=WHITE, bold=True)

    tw_text(page, f"#{rank}  —  APN {apn}", MARGIN, 22, fontsize=10.5, color=GOLD, bold=True)
    tw_text(page, owner[:58], MARGIN, 42, fontsize=9.5, color=WHITE, bold=True)
    if etype and etype != "N/A":
        tw_text(page, f"[{etype}]", MARGIN + min(len(owner[:58]) * 5.8, 320), 42,
                fontsize=8, color=GOLD)

    y = 74

    # ── Address ───────────────────────────────────────────────────────────────
    address = clean(row.get("address", ""), default="")
    if not address or "No Address" in address or address == "N/A":
        address = "[!] No situs address in public record — likely vacant land"
        addr_clr = ORANGE_MED
    else:
        addr_clr = DARK

    fill_rect(page, MARGIN, y, PAGE_W - 2 * MARGIN, 21, fill=LIGHT_BG)
    tw_text(page, "PROPERTY ADDRESS", MARGIN + 6, y + 8, fontsize=6.5, color=SLATE, bold=True)
    tw_text(page, address[:72], MARGIN + 115, y + 14, fontsize=8.5, color=addr_clr)
    y += 27

    # ── Financial metrics ─────────────────────────────────────────────────────
    hline(page, MARGIN, y, PAGE_W - 2 * MARGIN, color=GOLD, width=1.5)
    y += 8
    tw_text(page, "FINANCIAL METRICS", MARGIN, y + 2, fontsize=8, color=NAVY, bold=True)
    y += 13

    nav = row.get("nav_num", 0)
    mbt = row.get("max_bid_num", 0)
    fin = [
        ("Tax Balance Owed",  fmt_dollar(row.get("balance_num", 0)),  "Owed to county"),
        ("Minimum Bid",       fmt_dollar(row.get("min_bid_num", 0)),   "Starting bid"),
        ("Assessed Value",    fmt_dollar(nav) if nav > 0 else "[!] Not on roll", "County tax roll"),
        ("Max Safe Bid (70%)", fmt_dollar(mbt) if mbt > 0 else "[!] N/A",         "70% of assessed"),
        ("Bid / Value Ratio", clean(row.get("bid_to_value_pct", "")),  "Min bid ÷ assessed"),
    ]
    bw = (PAGE_W - 2 * MARGIN) / len(fin)
    for i, (lbl, val, sub) in enumerate(fin):
        x = MARGIN + i * bw
        fill_rect(page, x + 2, y, bw - 4, 54, fill=LIGHT_BG, stroke=NAVY_LIGHT, width=0.4)
        tw_text(page, lbl, x + 6, y + 13, fontsize=6.5, color=SLATE, bold=True)
        tw_text(page, val[:16], x + 6, y + 31, fontsize=9.5, color=NAVY, bold=True)
        tw_text(page, sub, x + 6, y + 46, fontsize=6.5, color=MED_GRAY)
    y += 62

    # ── Lien profile ──────────────────────────────────────────────────────────
    hline(page, MARGIN, y, PAGE_W - 2 * MARGIN, color=GOLD, width=1.5)
    y += 8
    tw_text(page, "LIEN & ENCUMBRANCE PROFILE", MARGIN, y + 2, fontsize=8, color=NAVY, bold=True)
    y += 13

    mortgages  = clean(row.get("total_open_mortgages", ""), default="0")
    lien_types = clean(row.get("open_lien_types", ""), default="None recorded")
    has_aor    = str(row.get("has_assignment_of_rents", "")).lower() in ("true", "1", "yes")
    has_nod    = str(row.get("notice_of_default_present", "")).lower() in ("true", "1", "yes")
    has_td     = str(row.get("has_trustee_deed", "")).lower() in ("true", "1", "yes")
    rec_cnt    = clean(row.get("recorder_doc_count", ""), default="0")

    lien_rows = [
        ("Open Mortgages",       mortgages,
         int(str(mortgages).split(".")[0]) > 0 if str(mortgages).replace(".","").isdigit() else False),
        ("Open Lien Types",      lien_types[:55],
         lien_types not in ("None recorded", "N/A")),
        ("Assignment of Rents",  "YES — Rental income pledged" if has_aor else "No", has_aor),
        ("Notice of Default",    "YES — Foreclosure initiated" if has_nod else "No", has_nod),
        ("Trustee's Deed Filed", "YES — Prior foreclosure" if has_td else "No", has_td),
        ("Recorder Documents",   str(rec_cnt) + " docs in chain", False),
    ]

    mid = MARGIN + (PAGE_W - 2 * MARGIN) / 2 + 4
    left, right = lien_rows[:3], lien_rows[3:]
    for sx, items in ((MARGIN, left), (mid, right)):
        for j, (lbl, val, alert) in enumerate(items):
            by = y + j * 21
            tw_text(page, lbl + ":", sx, by + 9, fontsize=7, color=SLATE, bold=True)
            tw_text(page, val, sx + 128, by + 9, fontsize=8,
                    color=RED_HIGH if alert else DARK)
    y += 3 * 21 + 8

    # ── Score rationale ───────────────────────────────────────────────────────
    hline(page, MARGIN, y, PAGE_W - 2 * MARGIN, color=GOLD, width=1.5)
    y += 8
    tw_text(page, "SCORE RATIONALE", MARGIN, y + 2, fontsize=8, color=NAVY, bold=True)
    y += 13

    reasons = clean(row.get("score_reasons", row.get("original_reasons", "")),
                    default="Tax Delinquency")
    parts   = [r.strip() for r in reasons.split(";")][:7]
    chip_w  = 78
    for j, part in enumerate(parts):
        cx = MARGIN + j * (chip_w + 4)
        fill_rect(page, cx, y, chip_w, 19, fill=LIGHT_BG, stroke=NAVY_LIGHT, width=0.4)
        tw_text(page, part[:15], cx + 4, y + 12, fontsize=6.5, color=NAVY)
    y += 28

    # ── Ownership profile ─────────────────────────────────────────────────────
    hline(page, MARGIN, y, PAGE_W - 2 * MARGIN, color=GOLD, width=1.5)
    y += 8
    tw_text(page, "OWNERSHIP PROFILE", MARGIN, y + 2, fontsize=8, color=NAVY, bold=True)
    y += 13

    conf = clean(row.get("owner_vesting_confidence", ""))
    try:
        conf_str = f"{float(conf)*100:.0f}%"
    except Exception:
        conf_str = conf

    vest = [
        ("Verified Owner",     owner[:45]),
        ("Entity Type",        etype),
        ("Vesting Confidence", conf_str),
        ("Parcel APN",         apn),
    ]
    for j, (lbl, val) in enumerate(vest):
        lx = MARGIN + (j % 2) * 265
        ly = y + (j // 2) * 18
        tw_text(page, lbl + ":", lx, ly + 10, fontsize=7, color=SLATE, bold=True)
        tw_text(page, val, lx + 120, ly + 10, fontsize=8, color=DARK)
    y += 42

    # ── Data quality flags ────────────────────────────────────────────────────
    flags = []
    if row.get("flag_no_addr"):
        flags.append("[!] No public situs address — likely vacant land or address not recorded")
    if row.get("flag_no_owner"):
        flags.append("[!] Owner name unresolved from recorder — skip trace recommended before contact")
    if row.get("flag_no_nav"):
        flags.append("[!] No assessed value on county roll — max bid threshold unavailable")

    if flags:
        bh = 14 + len(flags) * 13
        fill_rect(page, MARGIN, y, PAGE_W - 2 * MARGIN, bh, fill=(1.0, 0.97, 0.90))
        fill_rect(page, MARGIN, y, 4, bh, fill=AMBER)
        tw_text(page, "DATA GAPS", MARGIN + 10, y + 11, fontsize=7, color=AMBER, bold=True)
        for j, flag in enumerate(flags):
            tw_text(page, flag, MARGIN + 10, y + 22 + j * 13,
                    fontsize=7.5, color=(0.38, 0.28, 0.0))
        y += bh + 6

    # ── Footer ────────────────────────────────────────────────────────────────
    fill_rect(page, 0, PAGE_H - 36, PAGE_W, 36, fill=NAVY)
    tw_text(page,
            f"Property #{rank}  |  APN {apn}  |  Butte County Tax Auction — Aug 7–10, 2026",
            MARGIN, PAGE_H - 20, fontsize=7.5, color=MED_GRAY)
    tw_text(page,
            "Data: Butte County Assessor + Recorder (public record)  |  County Tax Auction Intelligence",
            MARGIN, PAGE_H - 9, fontsize=6.5, color=MED_GRAY)


# ── Report builder ────────────────────────────────────────────────────────────

def build_report(df, label, subtitle, filename, auction_date="Aug 7–10, 2026"):
    doc  = fitz.open()
    now  = datetime.now().strftime("%b %d, %Y %H:%M")
    tot  = df["balance_num"].sum()

    print(f"  Building: {label}  ({len(df)} properties)...")

    draw_cover(doc, label, subtitle, len(df), tot, auction_date, now)
    draw_summary(doc, df, f"{label} — Ranked Summary")

    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        draw_card(doc, rank, row)

    out = OUT_DIR / filename
    doc.save(str(out))
    doc.close()
    kb = os.path.getsize(out) // 1024
    print(f"  [OK] {filename} ({kb} KB)")
    return out


# -- Main ---------------------------------------------------------------------

def main():
    print("Loading and merging auction data...")
    df = load_data()
    print(f"  {len(df)} properties  |  "
          f"Score range {df['score_num'].min():.1f}-{df['score_num'].max():.1f}  |  "
          f"Total balance ${df['balance_num'].sum():,.0f}")
    print()

    # Tier 1 - Snapshot (Top 10)
    build_report(
        df.head(10).reset_index(drop=True),
        label="SNAPSHOT REPORT",
        subtitle="Top 10 Highest-Priority Auction Properties - Quick Reference",
        filename="Butte_Auction_Snapshot_Top10.pdf",
    )

    # Tier 2 - Full Report (score >= 70)
    tier2 = df[df["score_num"] >= 70].reset_index(drop=True)
    build_report(
        tier2,
        label="FULL INTELLIGENCE REPORT",
        subtitle="Top-Priority Properties (Score 70+) - Full Lien & Equity Analysis",
        filename="Butte_Auction_Full_Report_Top26.pdf",
    )

    # Tier 3 - War Room (all 105)
    build_report(
        df.reset_index(drop=True),
        label="WAR ROOM INTELLIGENCE PACK",
        subtitle="Complete Field - All 105 Auction Properties - Full Recorder Data",
        filename="Butte_Auction_WarRoom_All105.pdf",
    )

    print()
    print("=" * 60)
    print(f"Reports saved to:  {OUT_DIR}")
    print()
    print("PRODUCT TIERS")
    print("  Snapshot  (Top 10)  -> Butte_Auction_Snapshot_Top10.pdf       [$49]")
    print("  Full      (Top 26+) -> Butte_Auction_Full_Report_Top26.pdf    [$149]")
    print("  War Room  (All 105) -> Butte_Auction_WarRoom_All105.pdf       [$297]")


if __name__ == "__main__":
    main()

