"""
core/state.py

Per-county parcel state store (SQLite). Tracks what we know about every
parcel so the engine can decide what to pull next — and never re-pulls
what's already confirmed.

Tables:
  parcels   one row per APN; columns = data fields + per-field 'known' flags
  gaps      derived; which fields are missing and worth filling
  passes    log of each dynamic-loop pass (which action, what it filled)
"""
import sqlite3
from pathlib import Path

from .county import CountyConfig

# Field -> (source, value-priority 0-10, label)
# priority drives the dynamic loop: higher = pull sooner.
FIELD_DEFS = {
    "owner":     ("recorder", 10, "current owner"),
    "former_owner": ("recorder", 8, "former owner (excess proceeds)"),
    "tax_deed":  ("recorder", 9, "tax deed recorded"),
    "values":    ("assessor", 7, "assessed values"),
    "situs":     ("assessor", 5, "situs address"),
    "mailing":   ("assessor", 6, "mailing address"),
    "use":       ("assessor", 4, "use code"),
    "acreage":   ("assessor", 3, "acreage"),
    "current_doc_number": ("assessor", 2, "current recorded doc number (bridge to recorder)"),
    "auction_status": ("auction", 9, "on auction list"),
    "auction_min_bid": ("auction", 8, "auction minimum bid (amount due at sale)"),
    "auction_sold_price": ("auction", 8, "auction sale price (from county sold list)"),
    "auction_excess_proceeds": ("auction", 8, "county-published excess proceeds amount"),
    "deed_date": ("recorder", 6, "recording date of the tax deed"),
    "tax_verified_url": ("assessor", 5, "MPTS tax verification URL"),
    "tax_verified_at":  ("assessor", 5, "MPTS verification timestamp"),
}


class StateStore:
    def __init__(self, cfg: CountyConfig):
        self.cfg = cfg
        self.db_path = cfg.data_dir() / "state.sqlite"
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cols = ", ".join(f'"{f}" TEXT' for f in FIELD_DEFS)
        flags = ", ".join(f'"{f}_known" INTEGER DEFAULT 0' for f in FIELD_DEFS)
        checked = ", ".join(f'"{f}_checked" INTEGER DEFAULT 0' for f in FIELD_DEFS)
        cur.execute(f"CREATE TABLE IF NOT EXISTS parcels (apn TEXT PRIMARY KEY, {cols}, {flags}, {checked})")
        # migrate older DBs: add missing data columns and _known/_checked cols
        existing = {r[1] for r in cur.execute("PRAGMA table_info(parcels)")}
        for f in FIELD_DEFS:
            if f not in existing:
                cur.execute(f'ALTER TABLE parcels ADD COLUMN "{f}" TEXT')
            if f"{f}_known" not in existing:
                cur.execute(f'ALTER TABLE parcels ADD COLUMN "{f}_known" INTEGER DEFAULT 0')
            if f"{f}_checked" not in existing:
                cur.execute(f'ALTER TABLE parcels ADD COLUMN "{f}_checked" INTEGER DEFAULT 0')
        cur.execute(
            "CREATE TABLE IF NOT EXISTS passes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT, action TEXT, count INTEGER, detail TEXT)")
        self.conn.commit()

    # --- ingest ---
    def upsert_parcel(self, apn: str, fields: dict[str, str], commit: bool = True):
        cur = self.conn.cursor()
        cols = list(fields.keys())
        placeholders = ", ".join("?" for _ in cols)
        quoted = ", ".join('"{}"'.format(c) for c in cols)
        updates = ", ".join(
            '"{}"=CASE WHEN excluded."{}" != \'\' THEN excluded."{}" '
            'ELSE "{}" END'.format(c, c, c, c) for c in cols)
        cur.execute(
            f"INSERT INTO parcels (apn, {quoted}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(apn) DO UPDATE SET {updates}",
            [apn] + [fields[c] for c in cols])
        if commit:
            self.conn.commit()

    def mark_known(self, apn: str, field: str, commit: bool = True):
        self.conn.execute(
            f'UPDATE parcels SET "{field}_known"=1 WHERE apn=?', (apn,))
        if commit:
            self.conn.commit()

    def mark_checked(self, apn: str, field: str, commit: bool = True):
        """Record that a source was asked and confirmed it has no data for
        this field. Distinct from known: checked = source has nothing,
        known = a real value exists. Both end the gap, but only known
        counts toward filled data."""
        self.conn.execute(
            f'UPDATE parcels SET "{field}_checked"=1 WHERE apn=?', (apn,))
        if commit:
            self.conn.commit()

    def commit(self):
        self.conn.commit()
    # --- gap analysis ---
    def gaps(self) -> list[dict]:
        """Rank missing fields by value across the parcel set.
        A gap is any parcel that is not known AND not checked — i.e. the
        source was never asked. Checked (source confirmed nothing) is not
        a gap."""
        cur = self.conn.cursor()
        out = []
        for field, (source, prio, label) in FIELD_DEFS.items():
            n = cur.execute(
                f'SELECT COUNT(*) FROM parcels WHERE "{field}_known"=0 '
                f'AND "{field}_checked"=0').fetchone()[0]
            out.append({
                "field": field, "source": source, "priority": prio,
                "label": label, "missing": n,
            })
        out.sort(key=lambda g: g["priority"] * (g["missing"] > 0), reverse=True)
        return out

    def next_action(self, source: str | None = None) -> dict | None:
        """Highest-value gap we can fill right now (optionally filtered by
        source)."""
        for g in self.gaps():
            if g["missing"] > 0 and (source is None or g["source"] == source):
                return g
        return None

    def known_count(self, field: str) -> int:
        return self.conn.execute(
            f'SELECT COUNT(*) FROM parcels WHERE "{field}_known"=1').fetchone()[0]

    def count_with_value(self, field: str) -> int:
        """Count parcels where the field holds a real (non-empty, non-null)
        value — regardless of known flag."""
        return self.conn.execute(
            f'SELECT COUNT(*) FROM parcels WHERE "{field}" IS NOT NULL '
            f'AND TRIM("{field}") <> \'\'').fetchone()[0]

    def apns_missing(self, field: str, limit: int = 100000) -> list[str]:
        cur = self.conn.cursor()
        rows = cur.execute(
            f'SELECT apn FROM parcels WHERE "{field}_known"=0 AND '
            f'"{field}_checked"=0 ORDER BY apn LIMIT ?',
            (limit,)).fetchall()
        return [r[0] for r in rows]

    def apns_missing_prioritized(self, field: str, limit: int = 100000) -> list[str]:
        """Like apns_missing, but parcels that ALREADY sold at auction
        (auction_sold_price known) come first — those are the excess-
        proceeds parcels: the county published their surplus, the clock is
        running, and the recorder's deed parties tell us who to reach.
        Being first to those is the whole point."""
        cur = self.conn.cursor()
        rows = cur.execute(
            f'SELECT apn FROM parcels WHERE "{field}_known"=0 AND '
            f'"{field}_checked"=0 '
            f'ORDER BY CASE WHEN "auction_sold_price" != \'\' THEN 0 '
            f'ELSE 1 END, apn LIMIT ?',
            (limit,)).fetchall()
        return [r[0] for r in rows]

    def mark_all_checked(self, field: str, commit: bool = True) -> int:
        """Mark the field checked for every parcel (used when a source is
        absent entirely, so the loop stops offering it as a gap)."""
        n = self.conn.execute(
            f'UPDATE parcels SET "{field}_checked"=1 '
            f'WHERE "{field}_known"=0 AND "{field}_checked"=0').rowcount
        if commit:
            self.conn.commit()
        return n

    def mark_all_checked_for(self, field: str, apns: list[str],
                             commit: bool = True) -> int:
        """Mark the field checked for a specific set of APNs."""
        if not apns:
            return 0
        q = ",".join("?" for _ in apns)
        n = self.conn.execute(
            f'UPDATE parcels SET "{field}_checked"=1 '
            f'WHERE "{field}_known"=0 AND apn IN ({q})', apns).rowcount
        if commit:
            self.conn.commit()
        return n

    def apns_with(self, field: str, limit: int = 100000) -> list[str]:
        cur = self.conn.cursor()
        rows = cur.execute(
            f'SELECT apn FROM parcels WHERE "{field}_known"=1 ORDER BY apn LIMIT ?',
            (limit,)).fetchall()
        return [r[0] for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM parcels").fetchone()[0]

    # --- integrity: "blank spots" = marked known but empty ---
    def blank_spots(self, field: str | None = None) -> list[dict]:
        """Parcels whose field is flagged known yet the value is blank.
        A blank spot means a writer marked known without an actual value —
        a data-integrity violation, never a real 'unknown'."""
        cur = self.conn.cursor()
        cols = [field] if field else list(FIELD_DEFS)
        out = []
        for f in cols:
            rows = cur.execute(
                f'SELECT apn FROM parcels WHERE "{f}_known"=1 AND '
                f'("{f}" IS NULL OR "{f}" = \'\')').fetchall()
            for (apn,) in rows:
                out.append({"apn": apn, "field": f})
        return out

    def reset_known(self, apn: str, field: str, commit: bool = True):
        """Unmark a field so the loop re-pulls it (used to repair blank spots)."""
        self.conn.execute(
            f'UPDATE parcels SET "{field}_known"=0 WHERE apn=?', (apn,))
        if commit:
            self.conn.commit()

    def repair_blank_spots(self, field: str | None = None,
                           commit: bool = True) -> int:
        """Reset every blank spot to unknown so the source is re-queried.
        If `field` is given, only that field is repaired (used for
        self-correction, so we only re-pull what the current pass can fix)."""
        spots = self.blank_spots(field)
        for s in spots:
            self.reset_known(s["apn"], s["field"], commit=False)
        if commit:
            self.conn.commit()
        return len(spots)

    def known_count(self, field: str) -> int:
        return self.conn.execute(
            f'SELECT COUNT(*) FROM parcels WHERE "{field}_known"=1').fetchone()[0]

    def field_source(self, field: str) -> str:
        """Which source adapter fills a field (from FIELD_DEFS)."""
        return FIELD_DEFS[field][0]

    def log_pass(self, action: str, count: int, detail: str = ""):
        import datetime as dt
        self.conn.execute(
            "INSERT INTO passes (ts, action, count, detail) VALUES (?,?,?,?)",
            (dt.datetime.now().isoformat(timespec="seconds"), action, count, detail))
        self.conn.commit()

    def close(self):
        self.conn.close()

    def summary(self) -> dict:
        s = {"parcels": self.count()}
        for f in FIELD_DEFS:
            s[f] = self.known_count(f)
        return s
