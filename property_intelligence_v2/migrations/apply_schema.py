"""
Applies property_intelligence_v2's SQL migrations to a SQLite connection
the caller owns. No ORM (the repository doesn't already have one).

This is the ONLY code path that applies schema - production code and
tests both call apply_schema() against the same migration files. There
is no separate test-schema variant.

Usage:
    import sqlite3
    from apply_schema import apply_schema

    conn = sqlite3.connect(":memory:")   # or a real path, once authorized
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)

Importing this module does not create or touch any file - apply_schema()
must be called explicitly with a connection the caller owns.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

MIGRATIONS_DIR = Path(__file__).resolve().parent

# (version, filename, description) - append new tuples here as later
# migrations are added. Each filename must exist in this directory.
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "001_initial_schema.sql", "Phase 1: nine core contract tables (source_registry through exceptions)"),
    (2, "002_integrity_hardening.sql", "Phase 1 hardening: evidence/observation immutability triggers, typed "
                                        "observation_identifiers, evidence_disposition quarantine model, "
                                        "canonical_state_support + verification_status gating"),
    (3, "003_evidence_identity_unique.sql", "Phase 2: UNIQUE index enforcing raw_evidence's evidence-identity "
                                             "key (source_id, content_hash, source_url_or_identifier) for the "
                                             "legacy evidence importer"),
]

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1][0]


def _preflight_003(conn: sqlite3.Connection) -> None:
    """Fail clearly, before 003 runs, if raw_evidence already has rows that would
    violate its new UNIQUE(source_id, content_hash, source_url_or_identifier) index.

    SQLite's RAISE() is only valid inside a trigger body, so a plain SQL script
    cannot itself raise a custom message for this - this preflight is why 003's
    own .sql file contains no preflight statement of its own. Without this,
    CREATE UNIQUE INDEX would still fail on duplicate data (SQLite enforces the
    constraint directly), just with a less specific sqlite3.IntegrityError.
    """
    try:
        dupes = conn.execute(
            "SELECT source_id, content_hash, source_url_or_identifier, COUNT(*) AS c "
            "FROM raw_evidence GROUP BY source_id, content_hash, source_url_or_identifier HAVING c > 1"
        ).fetchall()
    except sqlite3.OperationalError:
        return  # raw_evidence doesn't exist yet on this connection - nothing to preflight
    if dupes:
        raise RuntimeError(
            "Migration 003 preflight failed: raw_evidence already contains "
            f"{len(dupes)} group(s) of rows sharing (source_id, content_hash, "
            "source_url_or_identifier). Resolve these duplicates before applying 003."
        )


# Migrations that need a Python-level check before their .sql file runs, keyed
# by version. Not every migration needs one - only present here when SQLite's
# own trigger-only RAISE() can't produce a clear enough failure by itself.
PREFLIGHT_CHECKS: dict[int, Callable[[sqlite3.Connection], None]] = {
    3: _preflight_003,
}


def apply_schema(conn: sqlite3.Connection, target_version: int = CURRENT_SCHEMA_VERSION) -> None:
    """Apply migrations up to target_version, in order, skipping any already recorded in schema_migrations.

    Each migration's DDL and its schema_migrations row are applied atomically,
    in one transaction: conn.executescript() alone does NOT provide this (each
    statement in a plain script autocommits individually as it runs - verified
    directly: a script with a valid CREATE TABLE followed by a failing
    statement leaves the valid table permanently created even though the
    script "failed"). Prefixing the script with an explicit "BEGIN;" and
    running the schema_migrations INSERT as a normal parameterized call
    afterward, before a single conn.commit(), keeps both in the one
    transaction that BEGIN opened - confirmed directly: if the INSERT fails,
    conn.rollback() undoes the DDL too, so a migration can never be left as
    "DDL applied, schema_migrations row missing."
    """
    applied = _get_applied_versions_or_none(conn)
    for version, filename, description in MIGRATIONS:
        if version > target_version:
            break
        if applied is not None and version in applied:
            continue
        if version in PREFLIGHT_CHECKS:
            PREFLIGHT_CHECKS[version](conn)
        sql = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
        try:
            conn.executescript("BEGIN;\n" + sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (version, datetime.now(timezone.utc).isoformat(), description),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied = _get_applied_versions_or_none(conn)


def get_applied_version(conn: sqlite3.Connection) -> int | None:
    versions = _get_applied_versions_or_none(conn)
    return max(versions) if versions else None


def _get_applied_versions_or_none(conn: sqlite3.Connection) -> set[int] | None:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {r[0] for r in rows}
    except sqlite3.OperationalError:
        return None  # schema_migrations doesn't exist yet - nothing applied
