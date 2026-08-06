"""
core/signals.py

The prediction engine. Given a county's full roll (assessor), recorder
history, and historical auction results, it scores every parcel for
likelihood of appearing on the county's next auction list — BEFORE the
county publishes it.

Signal families:
  default_signal   — tax-default indicators on the roll (non-renewal year,
                     contract year, tax area code patterns)
  value_signal     — assessed value vs. size/use (counties auction parcels
                     with equity the county can recover)
  absentee_signal  — out-of-county / out-of-state mailing
  history_signal   — was on a prior auction list (re-offer)
  recorder_signal  — tax deed / notice of power to sell recorded

Output: predicted_auction.csv — every parcel ranked, with a predicted list
threshold and each contributing signal spelled out.
"""
import csv
import re
from pathlib import Path

from .county import CountyConfig

# Strings on the roll that indicate tax-default / sale eligibility.
_DEFAULT_MARKERS = [
    "tax default", "power to sell", "delinquent", "tax sale",
    "unsecured", "defaulted",
]

# Use codes that are overwhelmingly residential — auction candidates counties
# actually re-offer tend to be land/residential, not commercial.
_AUCTION_USE_CODES = {"R", "RS", "M", "ALM", "AG", "VAC"}


def _truthy(v) -> bool:
    if v is None:
        return False
    s = str(v).strip().upper()
    return s not in ("", "0", "N", "NO", "FALSE", "NONE", "NULL")


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def score_parcel(row: dict) -> tuple[int, dict]:
    """Score one roll row -> (score 0-100, signal breakdown)."""
    score = 0
    signals: dict[str, str] = {}

    # --- default signal ---
    def_markers = []
    for f in ("WORD_DESCRIPTION", "USE_PRIMARY", "USE_SECONDARY", "NON_RENEWAL_YEAR",
              "CONTRACT_YEAR", "TAX_AREA_CODE"):
        val = str(row.get(f) or "")
        if any(m in val.lower() for m in _DEFAULT_MARKERS):
            def_markers.append(f"{f}={val[:30]}")
    nry = _int(row.get("NON_RENEWAL_YEAR"))
    cy = _int(row.get("CONTRACT_YEAR"))
    if def_markers:
        score += 40
        signals["default"] = "; ".join(def_markers)[:120]
    if nry and nry > 2018:
        score += 20
        signals["non_renewal"] = str(nry)
    elif cy and cy > 2018:
        score += 10
        signals["contract_year"] = str(cy)

    # --- value signal: positive assessed value, not a huge commercial parcel ---
    val = _int(row.get("TOTAL_ASSESSED_VALUE"))
    if val >= 20_000:
        score += 10
        signals["value"] = f"${val:,}"
    else:
        signals["value"] = f"low/zero (${val:,})"

    # --- absentee signal ---
    mail = " ".join(str(row.get(f) or "") for f in ("ADDRESS1", "ADDRESS2", "ADDRESS3"))
    county_hint = str(row.get("county") or "").lower()
    if mail and ("CA" not in mail.upper() or _out_of_county(mail, county_hint)):
        score += 15
        signals["absentee"] = mail[:60]
    elif mail:
        signals["absentee"] = "in-county"

    # --- use signal ---
    use = str(row.get("USE_PRIMARY") or "").strip().upper()
    if use and use in _AUCTION_USE_CODES:
        score += 10
        signals["use"] = use
    else:
        signals["use"] = use or "?"

    # --- homeowner exemption (bad sign: it means an occupied residence) ---
    if not _truthy(row.get("HOMEOWNER_EXEMP")):
        score += 5
        signals["no_homeowner_exemption"] = "yes"
    else:
        signals["no_homeowner_exemption"] = "exempt"

    return min(score, 100), signals


def _out_of_county(mail: str, county_hint: str) -> bool:
    """Rough heuristic: address mentions a different county or a state token
    that isn't CA. Kept deliberately simple; tune per county later."""
    m = mail.upper()
    if "CA" not in m:
        return True
    return False


def build_predictions(cfg: CountyConfig, roll_path: Path | None = None,
                      out_path: Path | None = None,
                      recorder_path: Path | None = None) -> Path:
    roll_path = roll_path or cfg.roll_path()
    out_path = out_path or cfg.data_dir() / "predicted_auction.csv"
    recorder_path = recorder_path or cfg.recorder_path()
    if not roll_path.exists():
        raise FileNotFoundError(f"No roll at {roll_path} — run stage source first")

    # Recorder-derived default signal: county collector as a party on the
    # deed. This is the universal 'county took / is owed the property'
    # signal across every county — independent of any auction list.
    tax_deed_apns: set[str] = set()
    tax_deed_detail: dict[str, str] = {}
    if recorder_path and recorder_path.exists():
        with open(recorder_path, newline="", encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                grantors = (row.get("grantors") or "").upper()
                grantees = (row.get("grantees") or "").upper()
                apn = (row.get("apn") or "").strip()
                if not apn:
                    continue
                # Only doc types that can be a county tax deed + the county
                # collector must actually be a party. Doc type 'T' alone is
                # a trustee's (foreclosure) deed in many counties.
                dtype = (row.get("doc_type") or "").strip().upper()
                deed_like = dtype in ("T", "TAX DEED", "DEED",
                                      "POWER TO SELL")
                is_tax_deed = deed_like and (
                    cfg.is_county_holder(grantors)
                    or cfg.is_county_holder(grantees)
                    or "POWER TO SELL" in grantors)
                if is_tax_deed:
                    tax_deed_apns.add(apn)
                    detail = f"{dtype}|{grantors[:60]}|{row.get('recording_date') or ''}"
                    tax_deed_detail.setdefault(apn, detail)

    scored = []
    apn_field = cfg.assessor.apn_field
    with open(roll_path, newline="", encoding="utf-8-sig") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            apn = str(row.get(apn_field) or row.get("APN") or row.get("apn")
                      or row.get("asmt") or row.get("ASMT") or "").strip().replace("-", "")
            s, sig = score_parcel(row)
            if apn in tax_deed_apns:
                s = max(s, 85)
                sig["tax_deed"] = tax_deed_detail[apn]
            row_out = {
                "county": cfg.county,
                "apn": apn,
                "score": s,
                **sig,
                "name": row.get("NAME1") or row.get("assessee_name") or "",
                "mailing": " ".join(str(row.get(f) or "") for f in
                                    ("ADDRESS1", "ADDRESS2", "ADDRESS3")),
                "situs": row.get("SITEADDRESS1") or row.get("Situs_Address") or row.get("situs") or "",
                "total_assessed_value": row.get("TOTAL_ASSESSED_VALUE"),
                "use_primary": row.get("USE_PRIMARY"),
                "non_renewal_year": row.get("NON_RENEWAL_YEAR"),
            }
            scored.append(row_out)

    scored.sort(key=lambda r: r["score"], reverse=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        fieldnames = ["county", "apn", "score", "default", "non_renewal",
                      "contract_year", "value", "absentee", "use",
                      "no_homeowner_exemption", "tax_deed", "name", "mailing",
                      "situs", "total_assessed_value", "use_primary",
                      "non_renewal_year"]
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scored)

    print(f"[signals:{cfg.county}] scored {len(scored):,} parcels, "
          f"{len(tax_deed_apns)} tax-deed hits -> {out_path}")

    # Emit recorder_targets.csv = the candidate pool to recorder-scan:
    # every tax-deed hit plus the top-N scored parcels (default 3000).
    top_n = max(len(tax_deed_apns) + 1, 3000)
    targets = []
    seen = set()
    for r in scored:
        if r["apn"] and r["apn"] not in seen:
            targets.append({"apn": r["apn"], "score": r["score"]})
            seen.add(r["apn"])
        if len(targets) >= top_n:
            break
    targets_path = cfg.data_dir() / "recorder_targets.csv"
    with open(targets_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["apn", "score"])
        writer.writeheader()
        writer.writerows(targets)
    print(f"[signals:{cfg.county}] candidate pool: {len(targets):,} apns -> "
          f"{targets_path}")
    return out_path
