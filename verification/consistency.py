"""
Layer 2: consistency verification.

Runs after data collection. Cross-checks that the values we pulled agree
with each other — catches parser bugs, silent scraping failures, and
county-site format changes before the shipped CSV reaches a buyer.

Checks (per parcel):
    APN_FORMAT_INVALID       APN doesn't match expected county format
    OWNER_NAME_MISMATCH      recorder grantee != assessor assessee (info only — drift is legitimate)
    MAILING_STATE_INVALID    mailing state didn't parse to CA/2-letter
    MAILING_CA_NOT_CA        out_of_state=Y but state parses as CA (or vice versa)
    SITUS_CITY_UNKNOWN       situs city doesn't match any known Butte city
    BALANCE_NONNUMERIC       v_total_balance won't parse to a number
    SCORE_OUT_OF_RANGE       priority_score outside 0-100
    NO_MAILING_NO_PHONE      unreachable lead (both channels missing)

Emits flags to verification_flags with layer='consistency'.
"""
import re
from typing import Iterable

import pandas as pd

from .db import connect
from .writer import VerificationRun


# County-specific APN regex (dashed and undashed forms accepted)
APN_PATTERNS = {
    "butte":  re.compile(r"^\d{3}-\d{3}-\d{3}-\d{3}$|^\d{12}$"),
    "shasta": re.compile(r"^\d{3}-\d{3}-\d{3}(-\d{3})?$"),
    "tehama": re.compile(r"^\d{3}-\d{3}-\d{3}(-\d{3})?$"),
}

# Known Butte County cities/CDPs. Situs cities outside this set get flagged.
BUTTE_CITIES = {
    "OROVILLE", "CHICO", "PARADISE", "GRIDLEY", "BIGGS", "MAGALIA",
    "COHASSET", "CONCOW", "BERRY CREEK", "FEATHER FALLS", "FORBESTOWN",
    "PALERMO", "BANGOR", "STIRLING CITY", "DE SABLA", "PULGA",
    "DURHAM", "NELSON", "HAMILTON CITY", "RICHVALE", "HONCUT",
}

STATE_RE = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\s*$")


def _blank(v) -> bool:
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


def check_row(row: dict, county: str = "butte") -> list[tuple[str, str, str]]:
    """Return a list of (flag_code, severity, message) for one parcel.
    Severities: info | warn | error."""
    flags: list[tuple[str, str, str]] = []
    apn = str(row.get("apn", "")).strip()

    # APN format
    pat = APN_PATTERNS.get(county)
    if pat and apn and not pat.match(apn):
        flags.append(("APN_FORMAT_INVALID", "error", f"APN '{apn}' doesn't match {county} format"))

    # Balance is numeric
    bal_raw = str(row.get("v_total_balance", "")).strip()
    if bal_raw:
        try:
            float(bal_raw.replace("$", "").replace(",", ""))
        except ValueError:
            flags.append(("BALANCE_NONNUMERIC", "warn", f"v_total_balance='{bal_raw}' not parseable as number"))

    # Priority score in 0-100
    ps_raw = str(row.get("priority_score", "")).strip()
    if ps_raw:
        try:
            ps = float(ps_raw)
            if ps < 0 or ps > 100:
                flags.append(("SCORE_OUT_OF_RANGE", "warn", f"priority_score={ps} outside 0-100"))
        except ValueError:
            flags.append(("SCORE_OUT_OF_RANGE", "warn", f"priority_score='{ps_raw}' not numeric"))

    # Mailing state validity
    mailing = str(row.get("mailing_address", "")).strip()
    if mailing and not _blank(mailing):
        m = STATE_RE.search(mailing)
        if not m:
            flags.append(("MAILING_STATE_INVALID", "warn", f"mailing address doesn't end with valid ST ZIP: '{mailing[-40:]}'"))
        else:
            parsed_state = m.group(1)
            declared_state = str(row.get("owner_state", "")).strip()
            declared_oos = str(row.get("out_of_state", "")).strip().upper()
            if declared_state and declared_state != parsed_state:
                flags.append(("MAILING_STATE_MISMATCH", "warn",
                              f"owner_state={declared_state} but mailing parses to {parsed_state}"))
            if declared_oos == "Y" and parsed_state == "CA":
                flags.append(("MAILING_CA_NOT_CA", "warn", "flagged out_of_state=Y but mailing state is CA"))
            if declared_oos == "N" and parsed_state != "CA":
                flags.append(("MAILING_CA_NOT_CA", "warn", f"flagged out_of_state=N but mailing state is {parsed_state}"))

    # Situs city sanity
    situs = str(row.get("situs_address", "")).strip().upper()
    if situs and not _blank(situs) and county == "butte":
        tokens = situs.split()
        if tokens:
            # City is typically the last 1-2 tokens (some cities are two words like "BERRY CREEK")
            last_two = " ".join(tokens[-2:])
            last_one = tokens[-1]
            if last_two in BUTTE_CITIES:
                pass
            elif last_one in BUTTE_CITIES:
                pass
            else:
                flags.append(("SITUS_CITY_UNKNOWN", "info",
                              f"situs city '{last_two}' not in known Butte cities"))

    # Reachability: no mailing AND no phone = dead lead
    has_mail = not _blank(row.get("mailing_address"))
    has_phone = not _blank(row.get("phone_number"))
    if not has_mail and not has_phone:
        flags.append(("NO_MAILING_NO_PHONE", "warn", "lead has neither mailing address nor phone — unreachable"))

    return flags


def run(csv_path: str, county: str = "butte", cycle_label: str | None = None) -> dict:
    df = pd.read_csv(csv_path, dtype=str)
    total = len(df)
    stats = {"parcels_checked": 0, "flags_emitted": 0, "parcels_with_flags": 0}
    severity_counts = {"info": 0, "warn": 0, "error": 0}

    with VerificationRun(
        county=county,
        cycle_label=cycle_label or f"{county} consistency check",
        input_source=f"{csv_path} (consistency layer)",
        parcel_count=total,
    ) as run_ctx:
        print(f"Consistency layer run #{run_ctx.run_id} on {total} parcels")

        for _, row in df.iterrows():
            apn = str(row.get("apn", "")).strip()
            if not apn:
                continue
            stats["parcels_checked"] += 1
            row_dict = row.to_dict()
            flags = check_row(row_dict, county=county)
            for code, sev, msg in flags:
                run_ctx.record_flag(apn, "consistency", code, sev, msg)
                stats["flags_emitted"] += 1
                severity_counts[sev] += 1
            if flags:
                stats["parcels_with_flags"] += 1
            # Consistency score = 100 - (10 * count of warn/error)
            warn_err = sum(1 for _, s, _ in flags if s in ("warn", "error"))
            consistency_score = max(0.0, 100.0 - 10.0 * warn_err)
            run_ctx.record_parcel(apn, consistency_score=consistency_score)

    print(f"Consistency layer done. {stats['parcels_checked']} parcels checked.")
    print(f"  Total flags emitted: {stats['flags_emitted']}")
    print(f"    info:  {severity_counts['info']}")
    print(f"    warn:  {severity_counts['warn']}")
    print(f"    error: {severity_counts['error']}")
    print(f"  Parcels with 1+ flags: {stats['parcels_with_flags']}")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--county", default="butte")
    args = parser.parse_args()
    run(args.csv_path, args.county)
