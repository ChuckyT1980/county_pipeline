#!/usr/bin/env python3
"""
Rebuild Tehama distressed property PDFs as acquisition-ready briefings with:
- Report-level metrics summary page
- Executive summary per lead
- Verified Signals (facts) vs Acquisition Notes (recommendations)
- Opportunity Score (renamed from Intent Score)
- Confidence indicator
- Priority A / Tier 1 / Immediate Review tiers
- Clickable assessor portal links on APN + badge
"""
import pdfplumber
import fitz
import re
import os

NAVY = (0.106, 0.169, 0.290)    # #1B2B4A
NAVY_LIGHT = (0.157, 0.224, 0.361)
GOLD = (0.784, 0.659, 0.306)    # #C8A84E
SLATE = (0.314, 0.357, 0.416)   # #505B6A
LIGHT_BG = (0.965, 0.969, 0.973)
WHITE = (1, 1, 1)
DARK = (0.133, 0.133, 0.133)
MED_GRAY = (0.565, 0.592, 0.627)
BORDER_LIGHT = (0.859, 0.871, 0.886)
GREEN_PRIORITY = (0.098, 0.463, 0.271)
ORANGE_TIER = (0.804, 0.373, 0.035)
BLUE_REVIEW = (0.176, 0.337, 0.620)

def extract_leads(pdf_path):
    leads = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full_text += t + "\n"

    blocks = re.split(r"(?=Lead #\d+:)", full_text)
    for block in blocks:
        if not block.strip():
            continue
        lead = {}
        strategy_buf = []
        in_strategy = False
        for line in block.split("\n"):
            l = line.strip()
            if "Parcel/APN:" in l:
                m = re.search(r"(\d{3}-\d{3}-\d{3}-\d{3})", l)
                if m:
                    lead["apn"] = m.group(1)
            if "First Name:" in l:
                lead["first_name"] = l.split("First Name:")[1].split("Parcel")[0].strip()
            if "Last Name:" in l:
                lead["last_name"] = l.split("Last Name:")[1].split("Property")[0].strip()
            if "Property Address:" in l:
                lead["property_address"] = l.split("Property Address:")[1].strip()
            if "Mailing Address:" in l:
                parts = l.split("Mailing Address:")[1].split("Intent Score")
                lead["mailing_address"] = parts[0].strip() if parts else ""
            if "Intent Score:" in l:
                m = re.search(r"Intent Score:\s*([\d.]+)", l)
                if m:
                    lead["opportunity_score"] = float(m.group(1))
            if "Distress Signals:" in l:
                lead["distress_signals"] = l.split("Distress Signals:")[1].strip()
            if "Suggested Acquisition Strategy:" in l:
                in_strategy = True
                continue
            if in_strategy:
                if (not l or "Lead #" in l or "First Name:" in l or "Last Name:" in l
                    or "Parcel/APN:" in l or "Property Address:" in l
                    or "Mailing Address:" in l or "Intent Score:" in l
                    or "Distress Signals:" in l or "Suggested Acquisition" in l
                    or "HOT LEAD" in l or "ACCELERATED" in l):
                    continue
                strategy_buf.append(l)
        if strategy_buf:
            lead["strategy"] = " ".join(strategy_buf)
        if lead.get("apn"):
            leads.append(lead)
    return leads

def parse_signals(text):
    data = {"liens": 0, "has_mortgage": False, "has_assignment_rents": False,
            "has_affidavit_death": False, "taxes_late": False, "tax_balance": 0.0,
            "out_of_state": False, "repeated_late": False}
    if not text:
        return data
    m = re.search(r"(\d+)\s*Active\s*Liens?", text, re.I)
    if m:
        data["liens"] = int(m.group(1))
    data["has_mortgage"] = "Has Mortgage" in text
    data["has_assignment_rents"] = "Assignment of Rents" in text
    data["has_affidavit_death"] = "Affidavit of Death" in text
    data["taxes_late"] = "LATE Taxes" in text
    data["out_of_state"] = "Out-of-state" in text
    m2 = re.search(r"Tax\s*Balance\s*\(?\$?([\d,.]+)\)?", text, re.I)
    if m2:
        try:
            data["tax_balance"] = float(m2.group(1).replace(",", ""))
        except:
            pass
    return data

def compute_confidence(signals):
    count = sum([1 for v in [signals["liens"] > 0, signals["has_mortgage"],
                             signals["has_assignment_rents"], signals["has_affidavit_death"],
                             signals["taxes_late"], signals["tax_balance"] > 0,
                             signals["out_of_state"]] if v])
    if count >= 5:
        return "High", 5
    elif count >= 3:
        return "Moderate", 3
    else:
        return "Limited", 1

def compute_tier(score):
    if score >= 10:
        return "Priority A", GREEN_PRIORITY
    elif score >= 4:
        return "Tier 1", ORANGE_TIER
    else:
        return "Immediate Review", BLUE_REVIEW

def build_exec_summary(lead, signals):
    parts = []
    if signals["liens"] > 0:
        parts.append(f"{signals['liens']} active lien{'s' if signals['liens'] > 1 else ''}")
    if signals["has_mortgage"]:
        parts.append("a recorded mortgage")
    if signals["has_assignment_rents"]:
        parts.append("assignment of rents")
    if signals["taxes_late"]:
        parts.append("continued tax delinquency")
    if signals["out_of_state"]:
        parts.append("out-of-state ownership")
    if not parts:
        return "Property identified for review."
    return "Multiple recorded distress indicators including " + ", ".join(parts) + ". Recommended for priority outreach."

def build_assessor_url(apn):
    compact = re.sub(r"\D", "", apn)
    return f"https://common1.mptsweb.com/MBC/tehama/tax/main/{compact}/2025/0000"

def wrap_text(text, font, fontsize, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = current + " " + w if current else w
        if font.text_length(test, fontsize=fontsize) < max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines

def render_metrics_page(doc, font, leads, A4_W, A4_H):
    MARGIN = 50
    BODY_W = A4_W - 2 * MARGIN
    page = doc.new_page(width=A4_W, height=A4_H)

    # ── Full-width navy header band ──
    page.draw_rect(fitz.Rect(0, 0, A4_W, 85), color=NAVY, fill=NAVY)
    page.draw_line(fitz.Point(0, 85), fitz.Point(A4_W, 85), color=GOLD, width=2)
    page.insert_text(fitz.Point(MARGIN, 35), "TEHAMA COUNTY", fontname="helv", fontsize=22, color=WHITE)
    page.insert_text(fitz.Point(MARGIN, 58), "Distressed Property Intelligence Report", fontname="helv", fontsize=13, color=GOLD)
    page.insert_text(fitz.Point(A4_W - MARGIN, 35), "July 2026", fontname="helv", fontsize=10, color=WHITE)
    sub_w = font.text_length("Prepared for Acquisition Team", fontsize=8)
    page.insert_text(fitz.Point(A4_W - MARGIN - sub_w, 52), "Prepared for Acquisition Team", fontname="helv", fontsize=8, color=GOLD)

    # ── Metrics section ──
    y = 110
    total_led = len(leads)
    total_score = sum(l.get("opportunity_score", 0) for l in leads)
    avg_score = round(total_score / total_led, 1) if total_led else 0
    s_all = [parse_signals(l.get("distress_signals", "")) for l in leads]

    metrics = [
        ("Total Leads", str(total_led), "\u2605"),
        ("Avg Opportunity Score", str(avg_score), "\u2191"),
        ("Total Active Liens", str(sum(s["liens"] for s in s_all)), "#"),
        ("Properties with Mortgages", str(sum(1 for s in s_all if s["has_mortgage"])), "\u25A3"),
        ("Assignment of Rents", str(sum(1 for s in s_all if s["has_assignment_rents"])), "\u25CB"),
        ("Out-of-State Owners", str(sum(1 for s in s_all if s["out_of_state"])), "\u21C6"),
        ("Counties", "1 (Tehama)", "\u25A0"),
        ("Affidavit of Death", str(sum(1 for s in s_all if s["has_affidavit_death"])), "\u2690"),
    ]

    page.insert_text(fitz.Point(MARGIN, y), "Report Summary", fontname="helv", fontsize=15, color=NAVY)
    page.draw_line(fitz.Point(MARGIN, y + 3), fitz.Point(MARGIN + 80, y + 3), color=GOLD, width=2)
    y += 24

    box_w = (BODY_W - 16) // 2
    box_h = 38
    for i, (label, val, icon) in enumerate(metrics):
        col = i % 2
        row = i // 2
        bx = MARGIN + col * (box_w + 16)
        by = y + row * (box_h + 10)
        page.draw_rect(fitz.Rect(bx, by, bx + box_w, by + box_h), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(bx, by, bx + 3, by + box_h), color=GOLD, fill=GOLD)
        page.insert_text(fitz.Point(bx + 12, by + 14), val, fontname="helv", fontsize=14, color=NAVY)
        page.insert_text(fitz.Point(bx + 12, by + 30), label, fontname="helv", fontsize=7, color=SLATE)

    # ── Tier distribution ──
    y += 4 * (box_h + 10) + 20
    page.draw_line(fitz.Point(MARGIN, y), fitz.Point(A4_W - MARGIN, y), color=BORDER_LIGHT, width=0.5)
    y += 14
    page.insert_text(fitz.Point(MARGIN, y), "Lead Distribution by Tier", fontname="helv", fontsize=13, color=NAVY)
    page.draw_line(fitz.Point(MARGIN, y + 3), fitz.Point(MARGIN + 110, y + 3), color=GOLD, width=2)
    y += 22

    tier_a = sum(1 for l in leads if l.get("opportunity_score", 0) >= 10)
    tier_1 = sum(1 for l in leads if 4 <= l.get("opportunity_score", 0) < 10)
    tier_2 = sum(1 for l in leads if l.get("opportunity_score", 0) < 4)

    for t_label, t_count, t_color in [
        ("Priority A            score 10+", tier_a, GREEN_PRIORITY),
        ("Tier 1                  score 4\u20139", tier_1, ORANGE_TIER),
        ("Immediate Review  score <4", tier_2, BLUE_REVIEW),
    ]:
        bw = int(BODY_W * t_count / max(total_led, 1))
        page.draw_rect(fitz.Rect(MARGIN, y, MARGIN + BODY_W, y + 20), color=BORDER_LIGHT, fill=LIGHT_BG, width=0.5)
        if t_count > 0:
            page.draw_rect(fitz.Rect(MARGIN, y, MARGIN + bw, y + 20), color=t_color, fill=t_color)
        page.insert_text(fitz.Point(MARGIN + 10, y + 14), f"{t_label}:  {t_count}", fontname="helv", fontsize=10, color=WHITE if t_count > 0 else SLATE)
        y += 26

    page.insert_text(fitz.Point(MARGIN, A4_H - 30), "Clickable APN links throughout this report open the Tehama County Assessor portal.", fontname="helv", fontsize=8, color=MED_GRAY)

def render_lead_page(doc, font, page, leads, page_idx, LEAD_PER_PAGE, A4_W, A4_H):
    MARGIN = 50
    BODY_W = A4_W - 2 * MARGIN
    HEADER_H = 60

    # ── Full-width navy header band ──
    page.draw_rect(fitz.Rect(0, 0, A4_W, HEADER_H), color=NAVY, fill=NAVY)
    page.draw_line(fitz.Point(0, HEADER_H), fitz.Point(A4_W, HEADER_H), color=GOLD, width=2)
    page.insert_text(fitz.Point(MARGIN, 22), "TEHAMA COUNTY", fontname="helv", fontsize=14, color=WHITE)
    page.insert_text(fitz.Point(MARGIN, 42), "Distressed Property Intelligence Report", fontname="helv", fontsize=10, color=GOLD)
    page.insert_text(fitz.Point(A4_W - MARGIN, 22), "July 2026", fontname="helv", fontsize=10, color=WHITE)
    page.insert_text(fitz.Point(A4_W - MARGIN, 40), f"Lead {page_idx + 1} of {len(leads)}", fontname="helv", fontsize=8, color=GOLD)

    y = HEADER_H + 24

    start = page_idx * LEAD_PER_PAGE
    end = min(start + LEAD_PER_PAGE, len(leads))

    for lead_idx in range(start, end):
        lead = leads[lead_idx]
        apn = lead.get("apn", "")
        url = build_assessor_url(apn)
        score = lead.get("opportunity_score", 0)
        signals = parse_signals(lead.get("distress_signals", ""))
        tier_label, tier_color = compute_tier(score)
        conf_label, conf_stars = compute_confidence(signals)

        # ── Tier header bar ──
        page.draw_rect(fitz.Rect(MARGIN, y, A4_W - MARGIN, y + 24), color=tier_color, fill=tier_color)
        page.insert_text(fitz.Point(MARGIN + 10, y + 16), f"Lead {lead_idx + 1}  |  {tier_label}", fontname="helv", fontsize=11, color=WHITE)
        y += 34

        # ── Executive summary card ──
        exec_text = build_exec_summary(lead, signals)
        exec_lines = wrap_text(exec_text, font, 10, BODY_W - 16)
        box_h = max(len(exec_lines) * 16 + 26, 44)
        page.draw_rect(fitz.Rect(MARGIN, y, A4_W - MARGIN, y + box_h), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_line(fitz.Point(MARGIN, y + 22), fitz.Point(A4_W - MARGIN, y + 22), color=BORDER_LIGHT, width=0.3)
        page.insert_text(fitz.Point(MARGIN + 8, y + 7), "Executive Summary", fontname="helv", fontsize=8, color=NAVY)
        for ei, el in enumerate(exec_lines):
            page.insert_text(fitz.Point(MARGIN + 8, y + 35 + ei * 16), el, fontname="helv", fontsize=10, color=DARK)
        y += box_h + 18

        # ── Two-column layout ──
        col_l = MARGIN
        col_w = BODY_W // 2 - 18
        col_r = MARGIN + BODY_W // 2 + 8
        ly = y
        ry = y

        # ── LEFT COLUMN ──
        # Owner section
        page.draw_rect(fitz.Rect(col_l, ly, col_l + col_w, ly + 58), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_l, ly, col_l + 3, ly + 58), color=GOLD, fill=GOLD)
        page.insert_text(fitz.Point(col_l + 12, ly + 10), "Owner", fontname="helv", fontsize=7, color=SLATE)
        name = f"{lead.get('last_name', '')}, {lead.get('first_name', '')}"
        page.insert_text(fitz.Point(col_l + 12, ly + 28), name, fontname="helv", fontsize=10, color=DARK)
        if lead.get("mailing_address"):
            page.insert_text(fitz.Point(col_l + 12, ly + 45), lead.get("mailing_address", ""), fontname="helv", fontsize=8, color=MED_GRAY)
        ly += 66

        # APN section
        page.draw_rect(fitz.Rect(col_l, ly, col_l + col_w, ly + 50), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_l, ly, col_l + 3, ly + 50), color=GOLD, fill=GOLD)
        page.insert_text(fitz.Point(col_l + 12, ly + 10), "APN", fontname="helv", fontsize=7, color=SLATE)
        page.insert_text(fitz.Point(col_l + 12, ly + 28), apn, fontname="helv", fontsize=11, color=NAVY)
        apn_w = font.text_length(apn, fontsize=11)
        page.draw_line(fitz.Point(col_l + 12, ly + 30), fitz.Point(col_l + 12 + apn_w, ly + 30), color=GOLD, width=1)
        page.insert_link({"kind": fitz.LINK_URI, "uri": url, "from": fitz.Rect(col_l + 11, ly + 17, col_l + 13 + apn_w, ly + 33)})
        bx = col_l + 14 + int(apn_w)
        bw = font.text_length("ASSESSOR", fontsize=8) + 14
        page.draw_rect(fitz.Rect(bx, ly + 18, bx + bw, ly + 33), color=NAVY, fill=NAVY)
        page.insert_text(fitz.Point(bx + 6, ly + 28), "ASSESSOR PORTAL", fontname="helv", fontsize=7, color=WHITE)
        page.insert_link({"kind": fitz.LINK_URI, "uri": url, "from": fitz.Rect(bx, ly + 18, bx + bw, ly + 33)})
        ly += 58

        # Property address
        page.draw_rect(fitz.Rect(col_l, ly, col_l + col_w, ly + 44), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_l, ly, col_l + 3, ly + 44), color=GOLD, fill=GOLD)
        page.insert_text(fitz.Point(col_l + 12, ly + 10), "Property Address", fontname="helv", fontsize=7, color=SLATE)
        addr = lead.get("property_address", "")
        page.insert_text(fitz.Point(col_l + 12, ly + 28), addr, fontname="helv", fontsize=10, color=DARK)
        ly += 52

        # ── RIGHT COLUMN ──
        # Opportunity Score
        page.draw_rect(fitz.Rect(col_r, ry, col_r + col_w, ry + 50), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + 3, ry + 50), color=tier_color, fill=tier_color)
        page.insert_text(fitz.Point(col_r + 12, ry + 10), "Opportunity Score", fontname="helv", fontsize=7, color=SLATE)
        score_str = str(int(score)) if score == int(score) else f"{score:.1f}"
        page.insert_text(fitz.Point(col_r + 12, ry + 35), score_str, fontname="helv", fontsize=20, color=tier_color)
        ry += 58

        # Data Confidence
        page.draw_rect(fitz.Rect(col_r, ry, col_r + col_w, ry + 44), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + 3, ry + 44), color=GOLD, fill=GOLD)
        page.insert_text(fitz.Point(col_r + 12, ry + 10), "Data Confidence", fontname="helv", fontsize=7, color=SLATE)
        stars = "\u2605" * conf_stars + "\u2606" * (5 - conf_stars)
        sc2 = GREEN_PRIORITY if conf_stars >= 4 else ORANGE_TIER if conf_stars >= 3 else MED_GRAY
        page.insert_text(fitz.Point(col_r + 12, ry + 30), stars, fontname="helv", fontsize=14, color=sc2)
        page.insert_text(fitz.Point(col_r + 12 + 90, ry + 30), conf_label, fontname="helv", fontsize=9, color=sc2)
        ry += 52

        # Verified Signals
        sig_items = []
        if signals["taxes_late"]:
            sig_items.append("Property Taxes Delinquent")
        if signals["liens"] > 0:
            sig_items.append(f"{signals['liens']} Active Lien{'s' if signals['liens'] > 1 else ''}")
        if signals["has_mortgage"]:
            sig_items.append("Mortgage Recorded")
        if signals["has_assignment_rents"]:
            sig_items.append("Assignment of Rents")
        if signals["has_affidavit_death"]:
            sig_items.append("Affidavit of Death")
        if signals["tax_balance"] > 0:
            sig_items.append(f"Tax Balance ${signals['tax_balance']:.2f}")
        if signals["out_of_state"]:
            sig_items.append("Out-of-State Owner")
        sig_h = max(len(sig_items) * 16 + 28, 44)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + col_w, ry + sig_h), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + 3, ry + sig_h), color=GREEN_PRIORITY, fill=GREEN_PRIORITY)
        page.insert_text(fitz.Point(col_r + 12, ry + 10), "Verified Signals", fontname="helv", fontsize=7, color=SLATE)
        for si, item in enumerate(sig_items):
            page.insert_text(fitz.Point(col_r + 12, ry + 28 + si * 16), "  \u2713  " + item, fontname="helv", fontsize=10, color=GREEN_PRIORITY)
        ry += sig_h + 8

        # Acquisition Notes
        notes = []
        if signals["liens"] > 0:
            notes.append(f"Multiple recorded financial obligations ({signals['liens']} active lien{'s' if signals['liens'] > 1 else ''}).")
        if signals["has_mortgage"]:
            notes.append("Mortgage exposure identified.")
        if signals["has_assignment_rents"]:
            notes.append("Rental income has been pledged (assignment of rents).")
        if signals["out_of_state"]:
            notes.append("Out-of-state owner \u2014 likely absentee, potentially motivated.")
        if signals["taxes_late"]:
            notes.append("Continued tax delinquency \u2014 consider early owner outreach.")
        if signals["has_affidavit_death"]:
            notes.append("Affidavit of Death on record \u2014 verify ownership status.")
        if not notes:
            notes.append("Property identified for further investigation.")
        note_lines = []
        for n in notes:
            note_lines.extend(wrap_text(n, font, 10, col_w - 20))
        note_h = max(len(note_lines) * 16 + 28, 44)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + col_w, ry + note_h), color=BORDER_LIGHT, fill=WHITE, width=0.5)
        page.draw_rect(fitz.Rect(col_r, ry, col_r + 3, ry + note_h), color=ORANGE_TIER, fill=ORANGE_TIER)
        page.insert_text(fitz.Point(col_r + 12, ry + 10), "Acquisition Notes", fontname="helv", fontsize=7, color=SLATE)
        for ni, nl in enumerate(note_lines):
            page.insert_text(fitz.Point(col_r + 12, ry + 28 + ni * 16), "  \u2022  " + nl, fontname="helv", fontsize=10, color=SLATE)
        ry += note_h

        y = max(ly, ry) + 14

    page.insert_text(fitz.Point(MARGIN, A4_H - 25),
        "Blue underlined APN numbers and ASSESSOR PORTAL badges are clickable links to the Tehama County Assessor portal.",
        fontname="helv", fontsize=7, color=MED_GRAY)

def render_pdf(leads, title, out_path):
    font = fitz.Font("helvetica")
    A4_W, A4_H = 595, 842
    doc = fitz.open()
    render_metrics_page(doc, font, leads, A4_W, A4_H)
    LEAD_PER_PAGE = 1
    n_pages = max(1, (len(leads) + LEAD_PER_PAGE - 1) // LEAD_PER_PAGE)
    for page_idx in range(n_pages):
        page = doc.new_page(width=A4_W, height=A4_H)
        render_lead_page(doc, font, page, leads, page_idx, LEAD_PER_PAGE, A4_W, A4_H)
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return out_path

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for pdf_name, title in [
        ("Tehama_Top_5_Distressed_Property_Intelligence_Report.pdf", "Tehama Top 5 Distressed Property Intelligence Report"),
        ("Tehama_35_Distressed_Property_Intelligence_Report.pdf", "Tehama 35 Distressed Property Intelligence Report"),
    ]:
        src = os.path.join(base_dir, pdf_name)
        if not os.path.exists(src):
            print(f"NOT FOUND: {src}")
            continue
        leads = extract_leads(src)
        print(f"{pdf_name}: {len(leads)} leads extracted")
        out_name = pdf_name.replace(".pdf", "_WITH_LINKS.pdf")
        render_pdf(leads, title, os.path.join(base_dir, out_name))
        print(f"  -> {out_name}")
