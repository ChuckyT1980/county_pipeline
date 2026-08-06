"""legacy_pdfs.py — parse Butte's legacy auction PDFs into training labels.

Two outputs, both in the standard schema:
  data/counties/butte/sold_results.csv    sales + excess summaries (pdf_jun2006
                                          ..pdf_jun2021) -> feeds the valuation
                                          pool and the excess-proceeds track.
  data/counties/butte/auction_lists.csv   list PDFs (sep2017..aug2026): apn,
                                          min_bid, status (sold/redeemed/
                                          withdrawn) -> auction-likelihood and
                                          redemption-risk labels.

Row classification is per-unit by $ amount count:
  1 amount  -> list row (min_bid)
  2 amounts -> sales_price, excess_proceeds
  3 amounts -> min_bid, sales_price, excess_proceeds
  4+        -> sales_price (first), excess_proceeds (last), fees dropped
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "tax_pipeline"
OUT = ROOT / "data" / "counties" / "butte"

APN_RE = re.compile(r"(\d{3}-\d{3}-\d{3}(?:-\d{3})?)")
AMT_RE = re.compile(r"\$\s*([\d][\d\s,.]*)(?:\s|$)")
STATUS_RE = re.compile(r"\b(Sold|Redeemed|Withdrawn)\b", re.IGNORECASE)
XMARK_RE = re.compile(r"\bX\b")
HYPHENS = str.maketrans("\u2010\u2011\u2012\u2013\u2014\u2015", "------")
YEAR_RE = re.compile(r"(20\d{2})")

SALES_FILES = [
    "pdf_jun2006.pdf", "pdf_jun2008.pdf", "pdf_jun2010.pdf",
    "pdf_jun2012.pdf", "pdf_jun2014.pdf",
]
LIST_FILES = [
    "pdf_sep2017.pdf", "pdf_sep2018.pdf", "pdf_sep2021.pdf",
    "pdf_jun2016.pdf", "pdf_jun2017.pdf", "pdf_jun2018.pdf",
    "pdf_jun2021.pdf", "pdf_jun2024.pdf", "pdf_sep2024_reoffer.pdf",
    "jun2026_sold.pdf", "reoffer_aug2026.pdf",
]
MONTH = {"jun": "06", "sep": "09", "aug": "08"}


def money(s: str):
    s = re.sub(r"\s", "", s).replace(",", "")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return ""


def page_units(text: str):
    """Split page text into (apn, rest) units anchored on APN tokens."""
    text = text.translate(HYPHENS)
    units = []
    cur_apn, cur = None, []
    for line in text.splitlines():
        m = APN_RE.search(line)
        if m:
            if cur_apn is not None:
                units.append((cur_apn, "\n".join(cur)))
            cur_apn = m.group(1).replace("-", "")
            cur = [line]
        elif cur_apn is not None:
            cur.append(line)
    if cur_apn is not None:
        units.append((cur_apn, "\n".join(cur)))
    return units


def amounts(text: str):
    out = []
    for m in AMT_RE.finditer(text):
        v = money(m.group(1))
        if v:
            out.append(v)
    return out


def parse_sales(path: Path):
    rows = []
    year = YEAR_RE.search(path.stem).group(1)
    month = MONTH.get(re.search(r"([a-z]{3})", path.stem).group(1), "06")
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for apn, rest in page_units(page.extract_text() or ""):
                amts = amounts(rest)
                n = len(amts)
                if n == 2:
                    rows.append((apn, "", amts[0], amts[1]))
                elif n == 3:
                    rows.append((apn, amts[0], amts[1], amts[2]))
                elif n >= 4:
                    rows.append((apn, "", amts[0], amts[-1]))
    return [(*r, f"{year}-{month}-01", path.name) for r in rows]


def parse_list(path: Path):
    rows = []
    year = YEAR_RE.search(path.stem).group(1)
    month = MONTH.get(re.search(r"([a-z]{3})", path.stem).group(1), "06")
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for apn, rest in page_units(page.extract_text() or ""):
                amts = amounts(rest)
                if not amts:
                    continue
                m = STATUS_RE.search(rest)
                status = m.group(1).lower() if m else (
                    "redeemed/withdrawn" if XMARK_RE.search(rest) else "")
                rows.append([apn, amts[0], status,
                             f"{year}-{month}-01", path.name])
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sales, lists = [], []
    for fn in SALES_FILES:
        rows = parse_sales(SRC / fn)
        sales += rows
        print(f"[pdf] {fn}: {len(rows)} sales")
    for fn in LIST_FILES:
        rows = parse_list(SRC / fn)
        lists += rows
        print(f"[pdf] {fn}: {len(rows)} listings")

    seen = set()
    sales_dedup = []
    for row in sales:
        key = (row[0], row[5])
        if key in seen:
            continue
        seen.add(key)
        sales_dedup.append(row)
    sales = sales_dedup

    csv_path = OUT / "sold_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["apn", "min_bid", "sales_price", "excess_proceeds",
                    "auction_date", "source_pdf"])
        w.writerows(sales)

    # true min bids from the PDFs, keyed by (year, apn) — the legacy CSV's
    # min_bid column is unreliable (holds sale amt or excess depending on
    # year), so the PDFs are the source of truth wherever they exist.
    true_min = {}
    for row in sales:
        if row[1]:
            true_min[(row[5][:4], row[0])] = row[1]
    for row in lists:
        true_min[(row[3][:4], row[0])] = row[1]

    # legacy CSV carries status / buyer / deed date / auction type
    csv_by_year_apn = {}
    legacy = SRC / "butte_all_auction_parcels.csv"
    if legacy.exists():
        with open(legacy, encoding="utf-8-sig") as fp:
            for r in csv.DictReader(fp):
                csv_by_year_apn[(r["year"], r["apn"].replace("-", ""))] = r

    # merge: CSV rows first (status/buyer/deed date), enriched with true
    # min bids; then any PDF listings the CSV missed.
    merged = {}
    for (year, apn), r in csv_by_year_apn.items():
        status = r["status"].strip().lower() or ""
        merged[(year, apn)] = [
            apn, year,
            (r["auction_type"] or "primary").strip(),
            "redeemed/withdrawn" if status == "redeemed" else status,
            true_min.get((year, apn), ""),
            (r["buyer_name"] or "").strip(),
            (r["deed_date"] or "").strip(),
        ]
    for row in lists:
        year, apn, status = row[3][:4], row[0], row[2]
        key = (year, apn)
        if key in merged:
            continue
        merged[key] = [apn, year, "primary", status,
                       true_min.get(key, ""), "", ""]

    list_path = OUT / "auction_lists.csv"
    with open(list_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["apn", "year", "auction_type", "status", "min_bid",
                    "buyer_name", "deed_date"])
        w.writerows(sorted(merged.values()))

    st = {}
    for row in merged.values():
        st[row[3]] = st.get(row[3], 0) + 1
    print(f"\n-> {csv_path}: {len(sales)} sales "
          f"(min_bid {sum(1 for r in sales if r[1])}, excess "
          f"{sum(1 for r in sales if r[3])})")
    print(f"-> {list_path}: {len(merged)} listings "
          f"(statuses: {st})")


if __name__ == "__main__":
    sys.exit(main())
