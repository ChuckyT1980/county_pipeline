"""
core/excess.py

Excess-proceeds deliverable for the unified engine. Reads the county
state store (sold results + tax-deed deed date + former owner/mailing
from the recorder) and emits:

  excess_proceeds/{county}_excess_{YYYY-MM-DD}.csv   all surplus parcels
  excess_proceeds/{county}_outreach_{YYYY-MM-DD}.csv claimable, sorted by
  excess amount (the former-owner outreach list)

Escheat clock: CA Rev & Tax Code gives former owners 1 year from the
deed recording date to claim the surplus; unclaimed funds then escheat
to the county.

INTEGRITY RULES (inherited from excess_proceeds/run_excess_finder.py):
  - Never fabricate: a row enters only if min_bid AND sold price are
    real, known values from the state store (county-published, not
    estimated). No default-value fallbacks.
  - Excess = county-published excess_proceeds when present, else
    sold_price - min_bid. Negative/zero surpluses are dropped.
  - Escheat deadline requires a real deed_date; rows without one are
    flagged DEED DATE UNKNOWN rather than guessed.
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

from .county import CountyConfig
from .state import StateStore

EXCESS_DIR = Path(__file__).resolve().parent.parent / "excess_proceeds"


def _parse_date(d: str):
    d = (d or "").strip()
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            pass
    # recorder timestamps: "07/01/2026 08:18 AM"
    for fmt in ("%m/%d/%Y %I:%M %p", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            pass
    return None


def _row_to_float(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def excess_report(cfg: CountyConfig, store: StateStore | None = None,
                  out_dir: Path | None = None) -> tuple[Path, Path]:
    own = store is None
    if own:
        store = StateStore(cfg)
    out_dir = out_dir or EXCESS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    cur = store.conn.cursor()
    rows = cur.execute(
        "SELECT apn, tax_deed, owner, former_owner, mailing, situs, "
        "       deed_date, auction_min_bid, auction_sold_price, "
        "       auction_excess_proceeds "
        "FROM parcels WHERE auction_sold_price IS NOT NULL "
        "AND auction_sold_price != ''").fetchall()

    today = datetime.now()
    results = []
    skipped = 0
    for (apn, tax_deed, owner, former_owner, mailing, situs,
         deed_date, min_bid, sold_price, published_excess) in rows:
        min_b = _row_to_float(min_bid)
        sold = _row_to_float(sold_price)
        if min_b is None or sold is None:
            skipped += 1  # incomplete sale data — never estimate
            continue

        excess = _row_to_float(published_excess)
        if excess is None:
            excess = sold - min_b
        if excess <= 0:
            continue

        deed_dt = _parse_date(deed_date)
        if deed_dt is None:
            escheat_deadline = ""
            days_until = None
            priority = "DEED DATE UNKNOWN"
        else:
            escheat = deed_dt + timedelta(days=365)
            days_until = (escheat - today).days
            escheat_deadline = escheat.strftime("%Y-%m-%d")
            if days_until < 0:
                priority = "EXPIRED / ESCHEATED"
            elif days_until <= 60:
                priority = "HIGH (URGENT)"
            elif days_until <= 180:
                priority = "MEDIUM"
            else:
                priority = "LOW"

        results.append({
            "apn": apn,
            "county": cfg.county,
            "tax_deed": tax_deed or "no",
            "deed_recorded_date": deed_dt.strftime("%Y-%m-%d") if deed_dt else "",
            "escheat_deadline": escheat_deadline,
            "days_until_escheat": days_until if days_until is not None else "",
            "min_bid": f"{min_b:,.2f}",
            "sold_price": f"{sold:,.2f}",
            "excess_amount": f"{excess:,.2f}",
            "priority_flag": priority,
            "former_owner_name": (former_owner or "").strip(),
            "current_owner_name": (owner or "").strip(),
            "former_owner_mailing": (mailing or "").strip(),
            "property_situs": (situs or "").strip(),
        })

    results.sort(key=lambda r: float(r["excess_amount"].replace(",", "")),
                 reverse=True)

    ts = datetime.now().strftime("%Y-%m-%d")
    full = out_dir / f"{cfg.county}_excess_{ts}.csv"
    outreach = out_dir / f"{cfg.county}_outreach_{ts}.csv"
    fields = list(results[0].keys()) if results else [
        "apn", "county", "tax_deed", "deed_recorded_date", "escheat_deadline",
        "days_until_escheat", "min_bid", "sold_price", "excess_amount",
        "priority_flag", "former_owner_name", "current_owner_name",
        "former_owner_mailing", "property_situs"]
    with open(full, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    claimable = [r for r in results
                 if r["days_until_escheat"] != "" and r["days_until_escheat"] != "-1"
                 and isinstance(r["days_until_escheat"], (int, str))
                 and str(r["days_until_escheat"]).lstrip("-").isdigit()
                 and int(r["days_until_escheat"]) >= -30]
    with open(outreach, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(claimable)

    total = sum(float(r["excess_amount"].replace(",", "")) for r in results)
    urgent = sum(1 for r in results if r["priority_flag"] == "HIGH (URGENT)")
    with_names = sum(1 for r in results if r["former_owner_name"])
    print(f"[excess:{cfg.county}] {len(results):,} surplus parcels "
          f"(${total:,.2f}); {urgent} urgent; {with_names} have former-owner "
          f"names; {skipped} skipped (incomplete sale data)")
    print(f"[excess:{cfg.county}] full: {full}")
    print(f"[excess:{cfg.county}] outreach: {outreach} ({len(claimable)} rows)")
    if own:
        store.close()
    return full, outreach


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", required=True)
    args = ap.parse_args()
    excess_report(CountyConfig.load(args.county))
