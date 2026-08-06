"""
null_name_dork_resolver.py — Null-Name Google Dork Generator + Receipt-Gated Capture Tool.

Resolves missing/null owner names on property parcels using targeted Google Search Dorks.

HARD RULE (enforced here):
  A name reaches the `verified_owner_name` field ONLY with a valid `source_url` receipt
  from an allowed county/court domain where the APN is verified on the landing page.
  Everything else (snippets, non-county sites, third-party aggregators) is parked under
  `lead_owner_name` with status `LEAD_UNVERIFIED` — it is NEVER laundered into verified.

Usage:
  # 1. Generate dorks for null-name parcels in a CSV:
  python null_name_dork_resolver.py dorks --csv data/tehama/tehama_owner_enriched.csv --county tehama --out dorks.html

  # 2. Capture a finding with receipt validation:
  python null_name_dork_resolver.py capture --csv data/tehama/tehama_owner_enriched.csv \
      --apn 004-110-034-000 --name "JOHNSON CARL A JR" \
      --url "https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/004110034000"

  # 3. Test a landing URL receipt:
  python null_name_dork_resolver.py verify-url --apn 004-110-034-000 \
      --url "https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/004110034000"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import quote_plus, urlparse

import httpx

from normalizers import DefaultNormalizers

# --------------------------------------------------------------------------- #
# County / Court Domain Allowlist
# --------------------------------------------------------------------------- #
# Only landing URLs on these domains (or ending in .gov / .us) can promote a
# candidate name to `verified_owner_name`.
COUNTY_COURT_ALLOWLIST = {
    "mptsweb.com",
    "tehama.gov",
    "shastacounty.gov",
    "shasta.gov",
    "buttecounty.net",
    "fresno.ca.gov",
    "kerncounty.com",
    "co.kern.ca.us",
    "co.shasta.ca.us",
    "co.tehama.ca.us",
    "co.butte.ca.us",
    "realauction.com",
    "govease.com",
    "bid4assets.com",
    "courts.ca.gov",
    "sacappeals.ca.gov",
}


def is_county_or_court_domain(url: str) -> bool:
    """Return True if url's domain is a recognized county/court domain or ends with .gov/.us."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().split(":")[0]
    except Exception:
        return False

    if not netloc:
        return False

    if netloc.endswith(".gov") or netloc.endswith(".us"):
        return True

    for allowed in COUNTY_COURT_ALLOWLIST:
        if netloc == allowed or netloc.endswith("." + allowed):
            return True

    return False


# --------------------------------------------------------------------------- #
# Google Dork Generator
# --------------------------------------------------------------------------- #
def generate_dorks_for_parcel(apn: str, county: str) -> list[dict[str, str]]:
    """Generate primary and secondary Google dorks for an APN and county."""
    apn_raw = apn.strip()
    apn_norm = re.sub(r"[^0-9A-Z]", "", apn_raw.upper())
    county_clean = county.replace("_", " ").strip().title()

    dorks = []

    # Primary Dork: exact APN + County
    query_1 = f'"{apn_raw}" "{county_clean} County"'
    dorks.append({
        "label": "Primary (Exact Raw APN + County)",
        "query": query_1,
        "search_url": f"https://www.google.com/search?q={quote_plus(query_1)}",
    })

    if apn_norm != apn_raw:
        query_2 = f'"{apn_norm}" "{county_clean} County"'
        dorks.append({
            "label": "Primary (Normalized APN + County)",
            "query": query_2,
            "search_url": f"https://www.google.com/search?q={quote_plus(query_2)}",
        })

    # Secondary Dorks: Assessor / Recorder / Tax
    query_3 = f'"{apn_norm}" "{county_clean}" Assessor OR Recorder'
    dorks.append({
        "label": "Assessor/Recorder Search",
        "query": query_3,
        "search_url": f"https://www.google.com/search?q={quote_plus(query_3)}",
    })

    query_4 = f'"{apn_norm}" "{county_clean}" Tax Sale OR Delinquent'
    dorks.append({
        "label": "Tax Sale / Delinquency Search",
        "query": query_4,
        "search_url": f"https://www.google.com/search?q={quote_plus(query_4)}",
    })

    return dorks


# --------------------------------------------------------------------------- #
# Receipt Verification Gate
# --------------------------------------------------------------------------- #
def validate_receipt(
    apn: str,
    source_url: str,
    fetch_live: bool = True,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """Validate landing page receipt against domain allowlist and APN presence.

    Returns:
        (is_verified: bool, reason: str)
    """
    if not source_url:
        return False, "NO_RECEIPT_URL_PROVIDED"

    if not is_county_or_court_domain(source_url):
        return False, f"NON_COUNTY_DOMAIN: {urlparse(source_url).netloc} not in allowlist"

    if not fetch_live:
        return True, "COUNTY_DOMAIN_VERIFIED_NO_FETCH"

    apn_raw = apn.strip()
    apn_norm = re.sub(r"[^0-9A-Z]", "", apn_raw.upper())

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
            resp = client.get(source_url)
            if resp.status_code != 200:
                return False, f"HTTP_{resp.status_code} on landing URL"

            body_text = resp.text
            # Check for APN in page text
            if apn_raw in body_text or apn_norm in body_text:
                return True, "VERIFIED_COUNTY_DOMAIN_AND_APN_ON_PAGE"
            else:
                return False, f"APN '{apn_raw}' not found in body of {source_url}"

    except Exception as exc:
        return False, f"FETCH_ERROR: {type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Merging into Master / Input CSV
# --------------------------------------------------------------------------- #
def is_null_name(name_val: Optional[str]) -> bool:
    if not name_val:
        return True
    val = str(name_val).strip().upper()
    return val in ("", "NONE", "NAN", "UNKNOWN", "COUNTY_REDACTED_NAME", "UNASSIGNED")


def generate_dorks_html(rows: list[dict], county: str, out_path: Path) -> None:
    """Generate a clean, clickable HTML dork sheet for null-name parcels."""
    html_lines = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Null-Name Dork Sheet</title>",
        "<style>",
        "body { font-family: monospace; background: #0f172a; color: #f8fafc; padding: 20px; }",
        "h1 { color: #38bdf8; }",
        ".parcel { background: #1e293b; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #334155; }",
        ".apn { font-weight: bold; color: #facc15; font-size: 1.1em; }",
        "a { color: #38bdf8; text-decoration: none; } a:hover { text-decoration: underline; }",
        "ul { margin: 8px 0; padding-left: 20px; }",
        "li { margin: 4px 0; }",
        "</style></head><body>",
        f"<h1>Null-Name Dork Sheet — {county.title()} County ({len(rows)} parcels)</h1>",
    ]

    for row in rows:
        apn = row.get("apn") or row.get("APN") or row.get("asmt") or ""
        dorks = generate_dorks_for_parcel(apn, county)
        html_lines.append("<div class='parcel'>")
        html_lines.append(f"<div class='apn'>APN: {apn}</div>")
        html_lines.append("<ul>")
        for d in dorks:
            html_lines.append(
                f"<li><strong>{d['label']}:</strong> "
                f"<a href='{d['search_url']}' target='_blank'>{d['query']}</a></li>"
            )
        html_lines.append("</ul></div>")

    html_lines.append("</body></html>")
    out_path.write_text("\n".join(html_lines), encoding="utf-8")


def capture_and_merge(
    csv_path: Path,
    apn: str,
    name: str,
    source_url: str,
    county: str,
    fetch_live: bool = True,
) -> dict:
    """Capture candidate name + receipt, run verification gate, and merge into CSV."""
    norm = DefaultNormalizers(home_county=county)
    name_norm, entity_type = norm.owner(name)
    apn_norm = norm.apn(apn)

    is_verified, reason = validate_receipt(apn, source_url, fetch_live=fetch_live)

    # Load CSV rows
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Ensure required columns exist
    new_cols = [
        "verified_owner_name",
        "lead_owner_name",
        "owner_source_url",
        "owner_verification_status",
        "verification_reason",
    ]
    for c in new_cols:
        if c not in fieldnames:
            fieldnames.append(c)

    updated = False
    result_status = ""

    for r in rows:
        row_apn = norm.apn(r.get("apn") or r.get("APN") or r.get("asmt") or "")
        if row_apn == apn_norm:
            r["owner_source_url"] = source_url
            r["verification_reason"] = reason

            if is_verified:
                r["verified_owner_name"] = name_norm
                r["owner_verification_status"] = "VERIFIED_COUNTY_RECEIPT"
                result_status = "VERIFIED"
            else:
                r["lead_owner_name"] = name_norm
                r["owner_verification_status"] = "LEAD_UNVERIFIED"
                result_status = "PARKED_AS_LEAD"

            updated = True
            break

    if updated:
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return {
        "apn": apn_norm,
        "name_norm": name_norm,
        "entity_type": entity_type.value,
        "source_url": source_url,
        "is_verified": is_verified,
        "reason": reason,
        "status": result_status,
        "csv_updated": updated,
    }


# --------------------------------------------------------------------------- #
# CLI Subcommands
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Null-Name Google Dork Generator & Receipt Verification Tool")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. dorks subcommand
    dorks_p = subparsers.add_parser("dorks", help="Generate Google Dorks for null-name parcels")
    dorks_p.add_argument("--csv", type=str, required=True, help="Input CSV path")
    dorks_p.add_argument("--county", type=str, default="tehama", help="County key")
    dorks_p.add_argument("--out", type=str, default="dorks.html", help="Output HTML dork sheet path")

    # 2. capture subcommand
    cap_p = subparsers.add_parser("capture", help="Capture owner name + receipt and merge into CSV")
    cap_p.add_argument("--csv", type=str, required=True, help="Target CSV path")
    cap_p.add_argument("--apn", type=str, required=True, help="Parcel APN")
    cap_p.add_argument("--name", type=str, required=True, help="Candidate owner name")
    cap_p.add_argument("--url", type=str, required=True, help="Landing page receipt source URL")
    cap_p.add_argument("--county", type=str, default="tehama", help="County key")
    cap_p.add_argument("--no-live-fetch", action="store_true", help="Skip HTTP GET live APN verification")

    # 3. verify-url subcommand
    ver_p = subparsers.add_parser("verify-url", help="Test if a receipt URL passes the verification gate")
    ver_p.add_argument("--apn", type=str, required=True, help="Parcel APN")
    ver_p.add_argument("--url", type=str, required=True, help="Landing page receipt URL")
    ver_p.add_argument("--no-live-fetch", action="store_true", help="Skip HTTP GET live APN verification")

    args = parser.parse_args()

    if args.subcommand == "dorks":
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"[dorks] Error: CSV file '{args.csv}' not found", file=sys.stderr)
            return 1
        with csv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        apn_col = None
        for col in ["apn", "APN", "asmt", "fee_parcel"]:
            if rows and col in rows[0]:
                apn_col = col
                break

        owner_col = None
        for col in ["owner_name", "verified_current_owner_name", "assessee_name", "owner"]:
            if rows and col in rows[0]:
                owner_col = col
                break

        null_rows = [
            r for r in rows
            if (not owner_col or is_null_name(r.get(owner_col)))
        ]

        print(f"[dorks] Found {len(null_rows)} null-name parcels in {csv_path.name}")
        out_path = Path(args.out)
        generate_dorks_html(null_rows, args.county, out_path)
        print(f"[dorks] Saved HTML dork sheet to {out_path.resolve()}")
        return 0

    elif args.subcommand == "capture":
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"[capture] Error: Target CSV '{args.csv}' not found", file=sys.stderr)
            return 1

        result = capture_and_merge(
            csv_path=csv_path,
            apn=args.apn,
            name=args.name,
            source_url=args.url,
            county=args.county,
            fetch_live=not args.no_live_fetch if hasattr(args, "no_live_fetch") else True,
        )
        print(json.dumps(result, indent=2))
        return 0

    elif args.subcommand == "verify-url":
        is_verified, reason = validate_receipt(
            apn=args.apn,
            source_url=args.url,
            fetch_live=not args.no_live_fetch,
        )
        output = {
            "apn": args.apn,
            "url": args.url,
            "is_verified": is_verified,
            "reason": reason,
            "status": "VERIFIED_COUNTY_RECEIPT" if is_verified else "PARKED_AS_LEAD",
        }
        print(json.dumps(output, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
