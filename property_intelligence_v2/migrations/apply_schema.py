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

MIGRATIONS_DIR = Path(__file__).resolve().parent

# (version, filename, description) - append new tuples here as later
# migrations are added. Each filename must exist in this directory.
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "001_initial_schema.sql", "Phase 1: nine core contract tables (source_registry through exceptions)"),
    (2, "002_integrity_hardening.sql", "Phase 1 hardening: evidence/observation immutability triggers, typed "
                                        "observation_identifiers, evidence_disposition quarantine model, "
                                        "canonical_state_support + verification_status gating"),
]

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1][0]


def apply_schema(conn: sqlite3.Connection, target_version: int = CURRENT_SCHEMA_VERSION) -> None:
    """Apply migrations up to target_version, in order, skipping any already recorded in schema_migrations."""
    applied = _get_applied_versions_or_none(conn)
    for version, filename, description in MIGRATIONS:
        if version > target_version:
            break
        if applied is not None and version in applied:
            continue
        sql = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
            (version, datetime.now(timezone.utc).isoformat(), description),
        )
        conn.commit()
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
