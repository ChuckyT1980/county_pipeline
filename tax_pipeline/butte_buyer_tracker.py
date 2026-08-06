"""
Butte County Tax Auction Repeat Buyer Tracker.
Parses all historical PDFs → matches sold parcels → identifies buyers via recorder.
"""
import re, json, csv, os, sys
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path

BASE = Path(__file__).parent

# ── Auction definitions ────────────────────────────────────────────────
AUCTIONS = [
    {"year": 2006, "month": 6, "auction_type": "primary",   "label": "June 2006",     "pdf": "pdf_jun2006.pdf"},
    {"year": 2008, "month": 6, "auction_type": "primary",   "label": "June 2008",     "pdf": "pdf_jun2008.pdf"},
    {"year": 2010, "month": 6, "auction_type": "primary",   "label": "June 2010",     "pdf": "pdf_jun2010.pdf"},
    {"year": 2012, "month": 6, "auction_type": "primary",   "label": "June 2012",     "pdf": "pdf_jun2012.pdf"},
    {"year": 2014, "month": 6, "auction_type": "primary",   "label": "June 2014",     "pdf": "pdf_jun2014.pdf"},
    {"year": 2016, "month": 6, "auction_type": "primary",   "label": "June 2016",     "pdf": "pdf_jun2016.pdf"},
    {"year": 2017, "month": 6, "auction_type": "primary",   "label": "June 2017",     "pdf": "pdf_jun2017.pdf"},
    {"year": 2017, "month": 9, "auction_type": "reoffer",   "label": "Sept 2017",    "pdf": "pdf_sep2017.pdf"},
    {"year": 2018, "month": 6, "auction_type": "primary",   "label": "June 2018",     "pdf": "pdf_jun2018.pdf"},
    {"year": 2018, "month": 9, "auction_type": "reoffer",   "label": "Sept 2018",    "pdf": "pdf_sep2018.pdf"},
    {"year": 2021, "month": 6, "auction_type": "primary",   "label": "June 2021",     "pdf": "pdf_jun2021.pdf"},
    {"year": 2021, "month": 9, "auction_type": "reoffer",   "label": "Sept 2021",    "pdf": "pdf_sep2021.pdf"},
    {"year": 2024, "month": 6, "auction_type": "primary",   "label": "June 2024",     "pdf": "pdf_jun2024.pdf"},
    {"year": 2024, "month": 9, "auction_type": "reoffer",   "label": "Sept 2024",    "pdf": "pdf_sep2024_reoffer.pdf"},
    {"year": 2026, "month": 6, "auction_type": "primary",   "label": "June 2026",     "pdf": "jun2026_sold.pdf"},
]

# Approximate auction end dates (used to define post-auction deed window)
# From Butte County historical data
AUCTION_DATES = {
    "June 2006":   datetime(2006, 6, 15),
    "June 2008":   datetime(2008, 6, 15),
    "June 2010":   datetime(2010, 6, 15),
    "June 2012":   datetime(2012, 6, 15),
    "June 2014":   datetime(2014, 6, 15),
    "June 2016":   datetime(2016, 6, 20),
    "June 2017":   datetime(2017, 6, 15),
    "Sept 2017":   datetime(2017, 9, 11),
    "June 2018":   datetime(2018, 6, 15),
    "Sept 2018":   datetime(2018, 9, 15),
    "June 2021":   datetime(2021, 6, 14),
    "Sept 2021":   datetime(2021, 9, 13),
    "June 2024":   datetime(2024, 6, 15),
    "Sept 2024":   datetime(2024, 9, 15),
    "June 2026":   datetime(2026, 6, 8),
}


# ── PDF Parser ─────────────────────────────────────────────────────────

def parse_pdf_text(path: Path) -> str:
    import fitz
    doc = fitz.open(str(path))
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def extract_apns(text: str) -> List[dict]:
    """Extract APN + Owner Name from PDF text.
    Handles multiple PDF formats across 2006-2026.
    """
    results = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    SKIP_HEADERS = {"APN", "OWNER", "SITUS ADDRESS", "LOCATION",
                    "MINIMUM BID", "MINIMU", "M BID",
                    "REDEEMED OR", "WITHDRAWN", "REDEEMED WITHDRAWN",
                    "SALE AMT", "EXCESS PROCEEDS", "ASSESSMENT NUMBER",
                    "PROPERTY ADDRESS", "PROPERTY", "JURISDICTION",
                    "FY 05/06 TX", "REDEMPTION", "TOTAL AUCTION",
                    "RESCISSION", "STATE", "DOC", "EXCESS", "AMOUNT",
                    "FEES", "FEE", "TRANS TAX", "PROCEEDS", "AMT"}

    def is_apn(s):
        return bool(re.match(r'^\d{3}-\d{3}-\d{3}-\d{3}(?:/\d{3}-\d{3}-\d{3}-\d{3})?$', s))

    def is_bid_line(s):
        return bool(re.match(r'^\$?\s*[\d,]+\.?\d*\s*$', s.strip())) or s == "$"

    def is_header(s):
        return s.upper() in SKIP_HEADERS

    i = 0
    while i < len(lines):
        line = lines[i]
        if not is_apn(line):
            i += 1
            continue

        apn = line
        owner_parts = []
        min_bid = 0.0
        status = ""
        done = False
        j = i + 1

        while j < len(lines) and not done:
            next_line = lines[j]

            if is_apn(next_line):
                done = True
                break
            if is_header(next_line):
                j += 1
                continue
            if is_bid_line(next_line):
                # Parse bid amount
                bid_str = next_line.replace("$", "").replace(",", "").strip()
                if bid_str:
                    try:
                        min_bid = float(bid_str)
                    except:
                        pass
                j += 1
                # Consume trailing $ lines and X/SOLD markers
                while j < len(lines):
                    tl = lines[j].strip()
                    if tl == "X":
                        status = "REDEEMED"
                        j += 1
                    elif tl.upper() == "SOLD":
                        status = "SOLD"
                        j += 1
                    elif tl == "$":
                        j += 1
                    elif re.match(r'^[\d,]+\.?\d*$', tl) and not is_apn(tl):
                        # Additional dollar amounts (excess proceeds format)
                        j += 1
                    elif tl.startswith("$") and is_bid_line(tl):
                        j += 1
                    else:
                        break
                done = True
                break

            # Check for X/SOLD on standalone lines interspersed with text
            if next_line.upper() == "SOLD":
                status = "SOLD"
                j += 1
                continue
            if next_line == "X":
                status = "REDEEMED"
                j += 1
                continue

            owner_parts.append(next_line)
            j += 1

        owner_name = " ".join(owner_parts)
        owner_name = re.sub(r'\s+', ' ', owner_name).strip()
        # Remove trailing junk from owner name
        for junk in ["$", "X", "SOLD"]:
            while owner_name.endswith(junk):
                owner_name = owner_name[:-len(junk)].strip()

        i = j
        results.append({
            "apn": apn,
            "owner_name": owner_name,
            "min_bid": min_bid,
            "status": status
        })

    return results


def parse_all_auctions() -> List[dict]:
    """Parse all auction PDFs and return unified list with auction metadata."""
    parcels = []
    for auction in AUCTIONS:
        pdf_path = BASE / auction["pdf"]
        if not pdf_path.exists():
            print(f"  WARN: {pdf_path.name} not found, skipping")
            continue
        text = parse_pdf_text(pdf_path)
        extracted = extract_apns(text)
        auction_date = AUCTION_DATES.get(auction["label"])

        # 2006-2014 PDFs are excess proceeds summaries — all parcels listed were SOLD
        force_sold = auction["year"] <= 2014

        for p in extracted:
            if force_sold and not p.get("status"):
                p["status"] = "SOLD"
            parcels.append({
                "year": auction["year"],
                "label": auction["label"],
                "auction_type": auction["auction_type"],
                "auction_date": auction_date.isoformat() if auction_date else "",
                **p
            })

        print(f"  {auction['label']}: {len(extracted)} parcels from {pdf_path.name}")

    return parcels


# ── Recorder buyer lookup ─────────────────────────────────────────────

def find_buyers_for_auction(parcels: List[dict], max_lookups: int = 9999) -> List[dict]:
    """
    Use Butte recorder adapter to find tax deed buyers for sold parcels.
    Deduplicates by owner name per auction to minimize recorder queries.
    """
    try:
        from butte_recorder_adapter import ButteRecorderAdapter
    except ImportError:
        print("  WARN: butte_recorder_adapter not available")
        return parcels

    # Deduplicate lookups: unique (owner_name_short, auction_label) pairs
    lookup_queue = []
    seen = set()
    for p in parcels:
        name = p.get("owner_name", "").strip()
        if not name:
            continue
        # Use last-name prefix for recorder search
        search_key = name.split(",")[0].strip() if "," in name else name.split()[0].strip()
        if not search_key or len(search_key) < 3:
            continue
        dedup_key = (search_key, p.get("label", ""))
        if dedup_key not in seen:
            seen.add(dedup_key)
            lookup_queue.append({**p, "search_key": search_key})

    print(f"  Unique owner searches needed: {len(lookup_queue)} (vs {len(parcels)} parcels)")

    adapter = None
    search_count = 0
    name_to_deeds = {}  # search_key -> list of relevant deeds

    try:
        adapter = ButteRecorderAdapter(headless=True)
        adapter.start()

        for item in lookup_queue:
            if search_count >= max_lookups:
                break

            search_key = item["search_key"]
            auction_label = item["label"]

            try:
                events = adapter.name_search(search_key)
                search_count += 1

                # Determine auction end date
                auction_end = None
                if item.get("auction_date"):
                    try:
                        auction_end = datetime.fromisoformat(item["auction_date"])
                    except:
                        pass

                # Filter for post-auction deeds
                deeds = []
                for ev in events:
                    if ev["role"] != "TRANSFER":
                        continue
                    if not ev.get("recorded_date"):
                        continue
                    try:
                        ev_date = datetime.fromisoformat(ev["recorded_date"])
                    except:
                        continue
                    if auction_end and ev_date < auction_end:
                        continue
                    # Grantor should contain the owner's last name
                    owner_last = item["owner_name"].split(",")[0].strip().upper()
                    if owner_last in ev.get("grantor", "").upper():
                        deeds.append(ev)

                if deeds:
                    name_to_deeds[search_key] = deeds

            except Exception as e:
                print(f"  WARN: search '{search_key}' failed: {e}")

    finally:
        if adapter:
            try:
                adapter.close()
            except:
                pass

    print(f"  Completed {search_count} searches, found deeds for {len(name_to_deeds)} owners")

    # Enrich parcels
    for p in parcels:
        name = p.get("owner_name", "").strip()
        if not name:
            continue
        search_key = name.split(",")[0].strip() if "," in name else name.split()[0].strip()
        deeds = name_to_deeds.get(search_key, [])
        if deeds:
            latest = max(deeds, key=lambda d: d.get("recorded_date", ""))
            p["buyer_name"] = latest.get("grantee", "")
            p["deed_date"] = latest.get("recorded_date", "")
            p["deed_doc_number"] = latest.get("doc_number", "")

    return parcels


# ── Analysis ──────────────────────────────────────────────────────────

def find_repeat_buyers(parcels: List[dict], min_purchases: int = 2) -> List[dict]:
    """Find buyers who purchased across multiple auctions."""
    from collections import Counter, defaultdict

    # Group by buyer (where known)
    buyer_auctions = defaultdict(set)
    buyer_parcels = defaultdict(list)
    buyer_years = defaultdict(set)

    for p in parcels:
        buyer = p.get("buyer_name", "").strip()
        if not buyer:
            continue
        buyer_auctions[buyer].add(p["label"])
        buyer_parcels[buyer].append(p)
        buyer_years[buyer].add(p["year"])

    # Filter to repeat buyers
    repeats = []
    for buyer, auctions_set in buyer_auctions.items():
        if len(auctions_set) >= min_purchases:
            repeats.append({
                "buyer": buyer,
                "auctions": sorted(auctions_set),
                "years": sorted(buyer_years[buyer]),
                "parcel_count": len(buyer_parcels[buyer]),
                "parcels": buyer_parcels[buyer]
            })

    repeats.sort(key=lambda r: -r["parcel_count"])
    return repeats


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("BUTTE COUNTY TAX AUCTION REPEAT BUYER TRACKER")
    print("=" * 60)

    # Step 1: Parse all PDFs
    print("\n[1/4] Parsing PDFs...")
    parcels = parse_all_auctions()
    print(f"  Total parcels extracted: {len(parcels)}")

    # Step 2: Identify sold parcels
    print("\n[2/4] Identifying sold parcels...")
    sold = [p for p in parcels if p.get("status") == "SOLD"]
    redeemed = [p for p in parcels if p.get("status") == "REDEEMED"]
    print(f"  Sold: {len(sold)}")
    print(f"  Redeemed/Withdrawn: {len(redeemed)}")
    print(f"  Status unknown: {len(parcels) - len(sold) - len(redeemed)}")

    # Step 3: Look up buyers via recorder (optional, controlled by --enrich flag)
    if "--enrich" in sys.argv:
        max_lk = int(sys.argv[sys.argv.index("--enrich") + 1]) if len(sys.argv) > sys.argv.index("--enrich") + 1 else 50
        print(f"\n[3/4] Enriching with recorder buyer lookups (max {max_lk})...")
        sold = find_buyers_for_auction(sold, max_lookups=max_lk)
        buyers_found = sum(1 for p in sold if p.get("buyer_name"))
        print(f"  Buyers found: {buyers_found}/{len(sold)}")

    # Step 4: Find repeat buyers
    print("\n[4/4] Analyzing repeat buyers...")
    repeats = find_repeat_buyers(sold)
    print(f"  Repeat buyers (>=2 auctions): {len(repeats)}")
    for r in repeats[:20]:
        print(f"    {r['buyer']}: {r['parcel_count']} parcels across {r['auctions']}")

    # Export
    out_csv = BASE / "butte_repeat_buyers.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["buyer", "parcel_count", "auction_count", "auctions", "years"])
        for r in repeats:
            w.writerow([
                r["buyer"], r["parcel_count"], len(r["auctions"]),
                "; ".join(r["auctions"]), "; ".join(str(y) for y in r["years"])
            ])
    print(f"\n  Exported to {out_csv.name}")

    # Export all parcels
    all_csv = BASE / "butte_all_auction_parcels.csv"
    with open(all_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "year", "auction_type", "apn", "owner_name",
                     "min_bid", "status", "buyer_name", "deed_date"])
        for p in parcels:
            w.writerow([
                p["label"], p["year"], p["auction_type"],
                p["apn"], p["owner_name"], p.get("min_bid", 0),
                p.get("status", ""), p.get("buyer_name", ""),
                p.get("deed_date", "")
            ])
    print(f"  All parcels exported to {all_csv.name}")


if __name__ == "__main__":
    main()
