"""
Ingest + cross-reference California county unclaimed estates lists.

Handles two pool types confirmed for Butte:
  - Fund 1070 (Unlocated Heirs)   — heir NAME is known, contact info missing
  - Fund 1071 (Unknown Heirs)     — no heir identified, needs genealogy

After ingest, runs cross-reference passes:
  1. Every decedent → check against current auction call sheet (butte CSV)
  2. Every decedent → check against verification.sqlite recorder graph
  3. (Future) Every decedent → check against surplus_opportunities
     (for post-auction surplus lists where the same person appears)

Usage:
    python -m surplus.estates ingest              # scrape + parse + upsert
    python -m surplus.estates crossref            # run all crossref passes
    python -m surplus.estates report              # dashboard-style summary
"""
import argparse
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import pdfplumber
import requests

from .db import connect, now


REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFICATION_DB = REPO_ROOT / "verification.sqlite"
BUTTE_CALL_SHEET = REPO_ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
SNAPSHOT_ROOT = Path(__file__).resolve().parent / "snapshots"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"


# ── Source config for estates ──────────────────────────────────────────

# Each entry declares one estate PDF for a county.
ESTATE_SOURCES = [
    {
        "county": "butte",
        "pool_type": "unlocated_heirs",
        "url": "https://www.buttecounty.net/DocumentCenter/View/18537/2026-Mar-FUND-1070-UNLOCATED-HEIRS",
        "parser": "butte_fund_1070",
    },
    {
        "county": "butte",
        "pool_type": "unknown_heirs",
        "url": "https://www.buttecounty.net/DocumentCenter/View/19049/26-May-Fund-1071-UNKNOWN-HEIRS",
        "parser": "butte_fund_1071",
    },
]

BUTTE_ESTATES_INDEX_URL = "https://www.buttecounty.net/1062/Unclaimed-Estates"


# ── Helpers ────────────────────────────────────────────────────────────

MONEY_RE  = re.compile(r"\$?\s?[\d][\d,]*\.\d{2}")
DATE_RE   = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
CASE_RE   = re.compile(r"\b(\d{2}PR-\d{5}|\d{4,7}[A-Z]\d?)\b")


def _to_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace(" ", "").strip())
    except (ValueError, TypeError):
        return None


def _to_iso(datestr):
    if not datestr:
        return None
    s = datestr.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _add_years(iso_date: str, years: int) -> str | None:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date)
        return d.replace(year=d.year + years).isoformat()
    except (ValueError, TypeError):
        return None


def _canon(name: str) -> str:
    """Uppercase, punctuation-stripped, whitespace-collapsed."""
    if not name:
        return ""
    s = re.sub(r"[^A-Z\s]", " ", str(name).upper())
    return " ".join(s.split())


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"    download failed: {type(e).__name__}: {str(e)[:120]}")
        return None


def _snapshot_path(county: str, pool_type: str, url: str) -> Path:
    d = SNAPSHOT_ROOT / county / pool_type
    d.mkdir(parents=True, exist_ok=True)
    fname = url.rstrip("/").split("/")[-1] or f"snapshot_{int(datetime.now().timestamp())}"
    if not fname.endswith((".pdf", ".html", ".htm")):
        fname += ".pdf"
    return d / fname


# ── Parsers ────────────────────────────────────────────────────────────

def parse_butte_fund_1070(pdf_bytes: bytes) -> list[dict]:
    """UNLOCATED HEIRS format:
        DATE | AMOUNT | DECEDENT NAME | DATE OF DEATH | IDENTIFIED HEIR | Case No/Probate code
    """
    out = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = ""
        for p in pdf.pages:
            text += (p.extract_text() or "") + "\n"

    for line in text.split("\n"):
        line = line.strip()
        # Line must start with a date and contain a $ amount and at least 2 more dates
        if not DATE_RE.match(line):
            continue
        money = MONEY_RE.findall(line)
        dates = DATE_RE.findall(line)
        if not money or len(dates) < 2:
            continue

        date_in = _to_iso(dates[0])
        amount  = _to_float(money[0])
        dod     = _to_iso(dates[1])
        case_match = CASE_RE.search(line)
        case_no = case_match.group(1) if case_match else ""

        # Extract name and heir by stripping known tokens
        clean = line
        for d in dates:
            clean = clean.replace(d, "")
        for m in money:
            clean = clean.replace(m, "")
        if case_no:
            clean = clean.replace(case_no, "")
        clean = re.sub(r"\s+", " ", clean).strip(" $,")

        # Format: "DECEDENT NAME | HEIR NAME(S)" — heir(s) usually comes after 2nd date
        # Split heuristic: after decedent name comes DOD, then heir. Since we already stripped dates,
        # what's left is "DECEDENT_NAME  HEIR_NAME[S]". Try to split by looking for surname repetition.
        parts = clean.split()
        if len(parts) < 4:
            continue

        # Best-effort split: try to find where decedent ends and heir begins.
        # Decedent name is usually first 2-4 tokens. Try each split point.
        # Prefer split where LAST NAME of decedent appears again in the heir portion (common pattern for children).
        decedent = ""
        heir = ""
        for split_at in range(2, min(5, len(parts) - 1)):
            candidate_dec = " ".join(parts[:split_at])
            candidate_heir = " ".join(parts[split_at:])
            dec_last = candidate_dec.split()[-1]
            if dec_last in candidate_heir.split():
                decedent = candidate_dec
                heir = candidate_heir
                break
        if not decedent:
            # Fallback: 3-token decedent, rest is heir
            decedent = " ".join(parts[:3]) if len(parts) >= 3 else parts[0]
            heir     = " ".join(parts[3:]) if len(parts) > 3 else ""

        out.append({
            "pool_type": "unlocated_heirs",
            "date_in": date_in,
            "amount": amount,
            "decedent_name": decedent,
            "date_of_death": dod,
            "identified_heir": heir,
            "probate_case_no": case_no,
        })
    return out


def parse_butte_fund_1071(pdf_bytes: bytes) -> list[dict]:
    """UNKNOWN HEIRS format:
        DATE IN | NAME | DATE OF DEATH | ESTATE TOTAL | Scheduled to Publish
    """
    out = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = ""
        for p in pdf.pages:
            text += (p.extract_text() or "") + "\n"

    for line in text.split("\n"):
        line = line.strip()
        if not DATE_RE.match(line):
            continue
        money = MONEY_RE.findall(line)
        dates = DATE_RE.findall(line)
        # PDF text extraction inserts weird spacing in the money field
        # e.g. "$ 2 2,098.79" for $22,098.79. Reconstruct by combining fragments.
        # Better strategy: extract the amount by pulling all $-adjacent number fragments and joining.
        # Simpler: find the $ and take everything after until end/date.
        amt_match = re.search(r"\$\s*([\d,\s]+\.\d{2})", line)
        amount = None
        if amt_match:
            amount = _to_float(amt_match.group(1))
        elif money:
            amount = _to_float(money[0])
        if len(dates) < 2 or amount is None:
            continue

        date_in = _to_iso(dates[0])
        dod     = _to_iso(dates[1])

        # Extract decedent name: between date_in and DOD
        # Line looks like: "8/10/2022 Erwin Larkins 12/20/2021 $ 6 32.05"
        # Strip date_in first, then find DOD position
        after_first_date = line.split(dates[0], 1)[1] if dates[0] in line else line
        before_dod = after_first_date.split(dates[1], 1)[0].strip()
        decedent = re.sub(r"\s+", " ", before_dod).strip(" $,")

        out.append({
            "pool_type": "unknown_heirs",
            "date_in": date_in,
            "amount": amount,
            "decedent_name": decedent,
            "date_of_death": dod,
            "identified_heir": None,
            "probate_case_no": None,
        })
    return out


PARSERS = {
    "butte_fund_1070": parse_butte_fund_1070,
    "butte_fund_1071": parse_butte_fund_1071,
}


# ── Ingest ─────────────────────────────────────────────────────────────

def ingest_all(dry_run: bool = False, county_filter: str | None = None) -> dict:
    total_stats = {"parsed": 0, "inserted": 0, "sources": 0}

    conn = connect()

    for src in ESTATE_SOURCES:
        if county_filter and src["county"] != county_filter:
            continue
        print(f"[{src['county']}/{src['pool_type']}] {src['url']}")

        content = _download(src["url"])
        if not content:
            continue

        parser = PARSERS.get(src["parser"])
        if not parser:
            print(f"    no parser for {src['parser']}")
            continue

        try:
            rows = parser(content)
        except Exception as e:
            print(f"    parse error: {type(e).__name__}: {str(e)[:120]}")
            continue

        print(f"    parsed {len(rows)} rows")
        total_stats["parsed"] += len(rows)
        total_stats["sources"] += 1

        if dry_run:
            for r in rows:
                print(f"    -> {r}")
            continue

        # Snapshot
        snap_path = _snapshot_path(src["county"], src["pool_type"], src["url"])
        with open(snap_path, "wb") as f:
            f.write(content)

        # Upsert
        for row in rows:
            escheat = _add_years(row.get("date_in"), 3)
            decedent_canonical = _canon(row.get("decedent_name"))
            heir_canonical     = _canon(row.get("identified_heir") or "")
            result = conn.execute(
                """
                INSERT INTO unclaimed_estates
                    (county, pool_type, decedent_name, decedent_canonical, date_of_death,
                     amount, identified_heir, identified_heir_canonical, probate_case_no,
                     date_in, escheat_date, source_url, source_snapshot_path,
                     source_first_seen, source_last_seen, ingested_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(county, pool_type, decedent_name, date_of_death) DO UPDATE SET
                    amount = excluded.amount,
                    identified_heir = excluded.identified_heir,
                    identified_heir_canonical = excluded.identified_heir_canonical,
                    probate_case_no = excluded.probate_case_no,
                    date_in = excluded.date_in,
                    escheat_date = excluded.escheat_date,
                    source_last_seen = excluded.source_last_seen,
                    source_url = excluded.source_url,
                    source_snapshot_path = excluded.source_snapshot_path,
                    updated_at = excluded.updated_at
                """,
                (
                    src["county"], row["pool_type"],
                    row.get("decedent_name"), decedent_canonical,
                    row.get("date_of_death"), row.get("amount"),
                    row.get("identified_heir"), heir_canonical,
                    row.get("probate_case_no"),
                    row.get("date_in"), escheat,
                    src["url"], str(snap_path),
                    now(), now(), now(), now(),
                ),
            )
            if result.rowcount > 0:
                total_stats["inserted"] += 1

    conn.commit()
    conn.close()
    return total_stats


# ── Cross-reference passes ────────────────────────────────────────────

def crossref_auction_call_sheet() -> list[dict]:
    """Check every decedent (and named heir) against current Butte call sheet."""
    if not BUTTE_CALL_SHEET.exists():
        return []
    df = pd.read_csv(BUTTE_CALL_SHEET, dtype=str)
    df["owner_canon"] = df["verified_current_owner_name"].apply(_canon)

    conn = connect()
    estates = conn.execute(
        "SELECT id, decedent_name, decedent_canonical, identified_heir, identified_heir_canonical, amount FROM unclaimed_estates"
    ).fetchall()

    matches = []
    for e in estates:
        # Match on decedent → auction parcel owner
        dec_canon = e["decedent_canonical"] or ""
        if dec_canon:
            m = df[df["owner_canon"] == dec_canon]
            for _, row in m.iterrows():
                matches.append({
                    "estate_id": e["id"],
                    "decedent": e["decedent_name"],
                    "amount": e["amount"],
                    "match_type": "decedent_is_current_auction_owner",
                    "matched_apn": row["apn"],
                    "matched_owner": row["verified_current_owner_name"],
                    "balance": row["v_total_balance"],
                })
        # Match on heir → auction parcel owner.
        # Heir field may contain multiple people separated by commas
        # (e.g. "Theodore Driver III, William Driver"). For each candidate heir,
        # require BOTH last-name AND first-name to match owner tokens — not
        # just a single-token substring, which produces false positives
        # like "JOHN Thibodeaux" matching every owner containing "JOHN".
        heir_raw = e["identified_heir"] or ""
        for h_name in re.split(r"[,;/]", heir_raw):
            h_canon = _canon(h_name)
            tokens = h_canon.split()
            if len(tokens) < 2:
                continue
            heir_last  = tokens[-1] if not tokens[-1].endswith("III") and not tokens[-1].endswith("II") else tokens[-2]
            heir_first = tokens[0]
            for _, row in df.iterrows():
                owner_tokens = str(row.get("owner_canon", "")).split()
                if len(owner_tokens) < 2:
                    continue
                # Butte format: "LAST FIRST [MIDDLE]"
                owner_last, owner_first = owner_tokens[0], owner_tokens[1]
                if owner_last == heir_last and owner_first == heir_first:
                    matches.append({
                        "estate_id": e["id"],
                        "decedent": e["decedent_name"],
                        "amount": e["amount"],
                        "match_type": "heir_is_current_auction_owner",
                        "matched_apn": row["apn"],
                        "matched_owner": row["verified_current_owner_name"],
                        "balance": row["v_total_balance"],
                    })

    # Persist matches
    for m in matches:
        conn.execute(
            """INSERT INTO estate_crossrefs (estate_id, match_kind, matched_entity_kind, matched_entity_id, matched_at, notes)
                 VALUES (?, ?, 'parcel', ?, ?, ?)""",
            (m["estate_id"], m["match_type"], m["matched_apn"], now(),
             f"{m['matched_owner']} @ balance={m['balance']}"),
        )
    conn.commit()
    conn.close()
    return matches


def crossref_recorder_graph() -> list[dict]:
    """Check every decedent/heir against verification.sqlite recorder graph."""
    if not VERIFICATION_DB.exists():
        return []
    conn = connect()
    vconn = sqlite3.connect(str(VERIFICATION_DB))
    vconn.row_factory = sqlite3.Row

    estates = conn.execute(
        """SELECT id, decedent_name, decedent_canonical,
                   identified_heir, identified_heir_canonical
             FROM unclaimed_estates"""
    ).fetchall()

    matches = []
    for e in estates:
        # Try exact decedent canonical match against graph nodes
        for label, canonical in (("decedent", e["decedent_canonical"]),
                                  ("heir", e["identified_heir_canonical"])):
            if not canonical:
                continue
            rows = vconn.execute(
                """SELECT p.id, p.display_name,
                          (SELECT COUNT(*) FROM graph_edges e2
                             WHERE e2.from_node_id = p.id AND e2.edge_kind IN ('grantor','grantee')) AS doc_count
                     FROM graph_nodes p
                    WHERE p.canonical_name = ? AND p.node_kind IN ('person','entity')""",
                (canonical,),
            ).fetchall()
            for r in rows:
                matches.append({
                    "estate_id": e["id"],
                    "decedent": e["decedent_name"],
                    "match_type": f"{label}_in_recorder_graph",
                    "graph_node_id": r["id"],
                    "graph_display": r["display_name"],
                    "doc_count": r["doc_count"],
                })

    # Persist
    for m in matches:
        conn.execute(
            """INSERT INTO estate_crossrefs (estate_id, match_kind, matched_entity_kind, matched_entity_id, matched_at, notes)
                 VALUES (?, ?, 'graph_node', ?, ?, ?)""",
            (m["estate_id"], m["match_type"], str(m["graph_node_id"]), now(),
             f"{m['graph_display']} — {m['doc_count']} docs in graph"),
        )
    conn.commit()
    vconn.close()
    conn.close()
    return matches


# ── Reports ────────────────────────────────────────────────────────────

def report() -> None:
    conn = connect()
    today = date.today().isoformat()

    print("=" * 76)
    print("UNCLAIMED ESTATES INVENTORY (across all counties)")
    print("=" * 76)

    for pool_type in ["unlocated_heirs", "unknown_heirs"]:
        rows = conn.execute(
            """SELECT county, pool_type, decedent_name, date_of_death,
                       amount, identified_heir, escheat_date,
                       CASE WHEN escheat_date > ? THEN 'workable' ELSE 'expired' END AS status_calc
                 FROM unclaimed_estates
                WHERE pool_type = ?
                ORDER BY amount DESC""",
            (today, pool_type),
        ).fetchall()
        if not rows:
            continue
        workable = [r for r in rows if r["status_calc"] == "workable"]
        expired  = [r for r in rows if r["status_calc"] == "expired"]
        total_workable = sum(r["amount"] or 0 for r in workable)
        print()
        print(f"POOL: {pool_type.upper()}")
        print(f"  Total estates:  {len(rows)}  ({len(workable)} workable, {len(expired)} expired)")
        print(f"  Workable $:     ${total_workable:,.2f}")
        print(f"  Your 10% fee:   ${total_workable * 0.10:,.2f}")
        print(f"  Top 10:")
        for r in rows[:10]:
            marker = " " if r["status_calc"] == "workable" else "X"
            heir = f" -> {r['identified_heir']}" if r["identified_heir"] else " (no heir named)"
            print(f"    {marker} ${r['amount']:>10,.2f}  {r['decedent_name']:35s}  died {r['date_of_death']}{heir}")

    # Cross-references
    crossrefs = conn.execute(
        """SELECT ec.match_kind, COUNT(*) AS n
             FROM estate_crossrefs ec
             GROUP BY ec.match_kind"""
    ).fetchall()
    print()
    print("CROSS-REFERENCE MATCHES:")
    if crossrefs:
        for c in crossrefs:
            print(f"  {c['match_kind']:45s} {c['n']}")
    else:
        print("  (no matches yet — run: python -m surplus.estates crossref)")

    conn.close()


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    sub.add_parser("crossref")
    sub.add_parser("report")
    args = p.parse_args()

    if args.cmd == "ingest":
        s = ingest_all()
        print(f"\nIngested {s['inserted']} rows from {s['sources']} sources.")
    elif args.cmd == "crossref":
        auction_matches = crossref_auction_call_sheet()
        graph_matches   = crossref_recorder_graph()
        print(f"Auction call-sheet matches: {len(auction_matches)}")
        for m in auction_matches:
            print(f"  {m}")
        print(f"\nRecorder graph matches: {len(graph_matches)}")
        for m in graph_matches:
            print(f"  {m}")
    elif args.cmd == "report":
        report()
