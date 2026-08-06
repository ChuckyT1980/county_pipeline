"""
Layer 4: ownership confidence.

Combines signals we already collect into a single 0-1 confidence that
the identified owner is really the current beneficial owner, plus an
ownership_class (INDIVIDUAL/TRUST/ESTATE/LLC/CORP/UNKNOWN) and a list
of ownership_flags surfaced to the buyer.

Confidence factors (each present adds/subtracts):
    +0.30  owner_name provenance == recorder_chain_grantee (authoritative)
    +0.15  owner_name provenance == asr_assessee (weaker fallback)
    +0.10  mailing address parses to a valid state
    +0.10  owner_state matches situs county state (in-state)
    +0.10  no consistency flags for this parcel
    +0.10  portfolio_apn_count >= 2 (correlates with genuine ownership persistence)
    -0.20  ownership_flags contains 'deceased_signal' or 'estate'
    -0.15  ownership_flags contains 'entity_dissolved' (once CA SOS wired)

Ownership_flags emitted:
    trust_involved         name contains TRUST / TRUSTEE
    estate                 name contains ESTATE / ESTATE OF
    deceased_signal        DECEASED / DECD / DEC'D in name
    corporate_entity       LLC / INC / CORP / LP / PARTNERSHIP
    multiple_owners        name contains multiple parties joined by AND / &
    executor_role          EXECUTOR / EXECUTRIX / ADMIN
    recent_transfer        (future — needs recorder chain with date parsing)
    senior_lien_survives   (future — needs full recorder chain)
"""
import json
import re
from typing import Iterable

import pandas as pd

from .db import connect
from .writer import VerificationRun


DECEASED_MARKERS = re.compile(r"\b(DECEASED|DECD|DEC'D|LATE)\b", re.IGNORECASE)
ESTATE_MARKERS = re.compile(r"\bESTATE( OF)?\b", re.IGNORECASE)
TRUST_MARKERS = re.compile(r"\b(TRUST|TRUSTEE|TR\b|LIVING TRUST|REVOCABLE TRUST)\b", re.IGNORECASE)
EXECUTOR_MARKERS = re.compile(r"\b(EXECUTOR|EXECUTRIX|ADMIN|ADMINISTRATOR)\b", re.IGNORECASE)
LLC_MARKERS = re.compile(r"\b(LLC|L\.L\.C|LTD)\b", re.IGNORECASE)
CORP_MARKERS = re.compile(r"\b(INC|CORP|CORPORATION|COMPANY|CO\b|PROPERTIES|HOLDINGS)\b", re.IGNORECASE)
MULTI_OWNER_RE = re.compile(r"\b(AND|&)\b", re.IGNORECASE)


def _blank(v) -> bool:
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


def classify_ownership(owner_name: str) -> tuple[str, list[str]]:
    """Return (ownership_class, ownership_flags) for a raw owner_name."""
    if _blank(owner_name):
        return "UNKNOWN", []
    name = str(owner_name).strip()
    flags: list[str] = []

    # Class classification (mutually exclusive, priority order)
    if ESTATE_MARKERS.search(name):
        cls = "ESTATE"
        flags.append("estate")
    elif LLC_MARKERS.search(name):
        cls = "LLC"
        flags.append("corporate_entity")
    elif CORP_MARKERS.search(name):
        cls = "CORP"
        flags.append("corporate_entity")
    elif TRUST_MARKERS.search(name):
        cls = "TRUST"
        flags.append("trust_involved")
    else:
        cls = "INDIVIDUAL"

    # Additional flags (non-mutually-exclusive)
    if DECEASED_MARKERS.search(name):
        flags.append("deceased_signal")
    if EXECUTOR_MARKERS.search(name):
        flags.append("executor_role")
    if MULTI_OWNER_RE.search(name):
        flags.append("multiple_owners")

    return cls, flags


def score_confidence(row: dict, provenance: dict) -> tuple[float, list[str]]:
    """
    row: CSV row as dict
    provenance: dict of {field_name: (source, confidence)} for this APN from
                the field_provenance table

    Returns (ownership_confidence 0..1, list of confidence_contributors for
    the audit trail).
    """
    conf = 0.0
    contributors: list[str] = []

    owner_source, owner_prov_conf = provenance.get("owner_name", (None, None))
    if owner_source == "recorder_chain_grantee":
        conf += 0.30
        contributors.append("recorder_grantee(+0.30)")
    elif owner_source == "asr_assessee":
        conf += 0.15
        contributors.append("asr_assessee(+0.15)")

    if not _blank(row.get("owner_state")):
        conf += 0.10
        contributors.append("mailing_state_valid(+0.10)")

    # In-state alignment
    owner_state = str(row.get("owner_state", "")).strip()
    if owner_state == "CA":
        conf += 0.10
        contributors.append("in_state(+0.10)")

    # No consistency issues
    apn = row.get("apn")
    if apn:
        cnt = _consistency_flag_count(apn)
        if cnt == 0:
            conf += 0.10
            contributors.append("no_consistency_flags(+0.10)")
        elif cnt >= 2:
            conf -= 0.05 * cnt
            contributors.append(f"consistency_flags(-{0.05 * cnt:.2f})")

    # Portfolio persistence — owning multiple parcels signals real active ownership
    try:
        portfolio = int(row.get("portfolio_apn_count") or 0)
        if portfolio >= 2:
            conf += 0.10
            contributors.append(f"portfolio_{portfolio}(+0.10)")
    except (ValueError, TypeError):
        pass

    # Distress signals from ownership_flags
    _, ownership_flags = classify_ownership(row.get("verified_current_owner_name") or "")
    if "deceased_signal" in ownership_flags:
        conf -= 0.20
        contributors.append("deceased(-0.20)")
    if "estate" in ownership_flags:
        conf -= 0.15
        contributors.append("estate(-0.15)")

    conf = max(0.0, min(1.0, conf))
    return conf, contributors


def _consistency_flag_count(apn: str) -> int:
    """Total warn+error consistency flags across all runs for this APN."""
    conn = connect()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM verification_flags
         WHERE apn = ? AND layer = 'consistency' AND severity IN ('warn','error')
        """,
        (apn,),
    ).fetchone()
    conn.close()
    return row["n"] or 0


def load_provenance_for_run(run_id: int) -> dict[str, dict[str, tuple[str, float]]]:
    """Latest provenance per (apn, field_name)."""
    conn = connect()
    rows = conn.execute(
        """
        SELECT fp.apn, fp.field_name, fp.source, fp.confidence
          FROM field_provenance fp
          JOIN (
              SELECT apn, field_name, MAX(id) AS max_id
                FROM field_provenance
               WHERE run_id = ?
               GROUP BY apn, field_name
          ) latest ON latest.max_id = fp.id
        """,
        (run_id,),
    ).fetchall()
    conn.close()
    out: dict[str, dict[str, tuple[str, float]]] = {}
    for r in rows:
        out.setdefault(r["apn"], {})[r["field_name"]] = (r["source"], r["confidence"])
    return out


def latest_enrichment_run(county: str) -> int | None:
    conn = connect()
    row = conn.execute(
        """
        SELECT id FROM verification_runs
         WHERE county = ? AND status = 'completed'
           AND cycle_label LIKE '%address enrichment%'
         ORDER BY started_at DESC LIMIT 1
        """,
        (county,),
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def run(csv_path: str, county: str = "butte") -> dict:
    df = pd.read_csv(csv_path, dtype=str)
    for col in ("ownership_class", "ownership_confidence", "ownership_flags", "ownership_contributors"):
        if col not in df.columns:
            df[col] = ""

    enrichment_run_id = latest_enrichment_run(county)
    provenance_by_apn = load_provenance_for_run(enrichment_run_id) if enrichment_run_id else {}

    total = len(df)
    stats = {"parcels": 0, "high_conf": 0, "mid_conf": 0, "low_conf": 0}
    class_counts: dict[str, int] = {}

    with VerificationRun(
        county=county,
        cycle_label=f"{county} ownership confidence",
        input_source=csv_path,
        parcel_count=total,
    ) as run_ctx:
        print(f"Ownership layer run #{run_ctx.run_id} on {total} parcels")

        for idx, row in df.iterrows():
            apn = str(row.get("apn", "")).strip()
            if not apn:
                continue
            row_dict = row.to_dict()
            cls, flags = classify_ownership(row_dict.get("verified_current_owner_name") or "")
            conf, contributors = score_confidence(row_dict, provenance_by_apn.get(apn, {}))

            df.at[idx, "ownership_class"] = cls
            df.at[idx, "ownership_confidence"] = f"{conf:.2f}"
            df.at[idx, "ownership_flags"] = ",".join(flags)
            df.at[idx, "ownership_contributors"] = ",".join(contributors)

            run_ctx.record_parcel(
                apn,
                ownership_confidence=conf,
                ownership_class=cls,
                ownership_flags=flags,
            )
            for f in flags:
                if f in ("deceased_signal", "estate", "corporate_entity"):
                    run_ctx.record_flag(apn, "ownership", f"OWNER_{f.upper()}", "info",
                                         f"owner={row_dict.get('verified_current_owner_name','')[:60]}")

            stats["parcels"] += 1
            if conf >= 0.75:
                stats["high_conf"] += 1
            elif conf >= 0.5:
                stats["mid_conf"] += 1
            else:
                stats["low_conf"] += 1
            class_counts[cls] = class_counts.get(cls, 0) + 1

    df.to_csv(csv_path, index=False)

    print(f"Ownership layer done. {stats['parcels']} parcels classified.")
    print(f"  High confidence (>= 0.75):  {stats['high_conf']}")
    print(f"  Mid confidence  (0.5-0.75): {stats['mid_conf']}")
    print(f"  Low confidence  (< 0.5):    {stats['low_conf']}")
    print(f"  Class breakdown: {class_counts}")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--county", default="butte")
    args = parser.parse_args()
    run(args.csv_path, args.county)
