"""
Write API for pipeline stages. Kept small, stateless, and forgiving —
verification is a sidecar, not a blocker; a failure here should NOT stop
the pipeline from producing output.
"""
import json
from datetime import datetime, timezone
from typing import Iterable

from .db import connect


PIPELINE_VERSION = "0.1.0"  # bump when the write contract changes


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VerificationRun:
    """
    Context manager for a single pipeline cycle's verification run.

    Any exception inside the `with` block is logged as run status='failed'
    but re-raised so callers can decide what to do. Successful completion
    updates status='completed' and computes summary averages.
    """

    def __init__(
        self,
        county: str,
        cycle_label: str | None = None,
        input_source: str | None = None,
        parcel_count: int | None = None,
        db_path=None,
    ):
        self.county = county
        self.cycle_label = cycle_label
        self.input_source = input_source
        self.parcel_count = parcel_count
        self._db_path = db_path
        self._conn = None
        self.run_id: int | None = None

    def __enter__(self) -> "VerificationRun":
        self._conn = connect(self._db_path)
        cur = self._conn.execute(
            """
            INSERT INTO verification_runs
                (started_at, county, cycle_label, pipeline_version, input_source, parcel_count, status)
            VALUES (?, ?, ?, ?, ?, ?, 'in_progress')
            """,
            (_now(), self.county, self.cycle_label, PIPELINE_VERSION, self.input_source, self.parcel_count),
        )
        self.run_id = cur.lastrowid
        self._conn.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            status = "failed" if exc_type else "completed"
            averages = self._compute_averages() if status == "completed" else (None, None, None)
            self._conn.execute(
                """
                UPDATE verification_runs
                   SET finished_at = ?, status = ?,
                       completeness_avg = ?, consistency_avg = ?, ownership_confidence_avg = ?
                 WHERE id = ?
                """,
                (_now(), status, *averages, self.run_id),
            )
            self._conn.commit()
        finally:
            self._conn.close()
            self._conn = None
        return False  # never suppress

    # ── write API ────────────────────────────────────────────────────────

    def record_field(
        self,
        apn: str,
        field_name: str,
        field_value,
        source: str,
        confidence: float,
        notes: str | None = None,
    ) -> None:
        """Log one field's provenance. Called per (parcel, field) filled."""
        val = None if field_value is None else str(field_value)
        self._conn.execute(
            """
            INSERT INTO field_provenance
                (run_id, apn, field_name, field_value, source, confidence, fetched_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.run_id, apn, field_name, val, source, float(confidence), _now(), notes),
        )
        self._conn.commit()

    def record_parcel(
        self,
        apn: str,
        sources_expected: Iterable[str] | None = None,
        sources_succeeded: Iterable[str] | None = None,
        completeness_score: float | None = None,
        consistency_score: float | None = None,
        ownership_confidence: float | None = None,
        ownership_class: str | None = None,
        ownership_flags: Iterable[str] | None = None,
    ) -> None:
        """Log one parcel's roll-up verification record. Called once per parcel."""
        expected = list(sources_expected) if sources_expected else []
        succeeded = list(sources_succeeded) if sources_succeeded else []

        # Auto-derive completeness if not provided but we have both source lists
        if completeness_score is None and expected:
            completeness_score = 100.0 * len(succeeded) / len(expected)

        flags_json = json.dumps(list(ownership_flags)) if ownership_flags else None
        self._conn.execute(
            """
            INSERT INTO parcel_verifications
                (run_id, apn, county, completeness_score, consistency_score,
                 ownership_confidence, ownership_class, ownership_flags,
                 sources_expected, sources_succeeded, verified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, apn) DO UPDATE SET
                completeness_score = excluded.completeness_score,
                consistency_score = excluded.consistency_score,
                ownership_confidence = excluded.ownership_confidence,
                ownership_class = excluded.ownership_class,
                ownership_flags = excluded.ownership_flags,
                sources_expected = excluded.sources_expected,
                sources_succeeded = excluded.sources_succeeded,
                verified_at = excluded.verified_at
            """,
            (
                self.run_id, apn, self.county,
                completeness_score, consistency_score,
                ownership_confidence, ownership_class, flags_json,
                json.dumps(expected), json.dumps(succeeded),
                _now(),
            ),
        )
        self._conn.commit()

    def record_flag(
        self,
        apn: str,
        layer: str,
        flag_code: str,
        severity: str = "warn",
        message: str | None = None,
    ) -> None:
        """Log a flag (something that failed a check). Called by any layer."""
        assert layer in {"completeness", "consistency", "ownership", "outcome"}, layer
        assert severity in {"info", "warn", "error"}, severity
        self._conn.execute(
            """
            INSERT INTO verification_flags
                (run_id, apn, layer, flag_code, severity, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.run_id, apn, layer, flag_code, severity, message, _now()),
        )
        self._conn.commit()

    # ── read helpers for the same run ────────────────────────────────────

    def summary(self) -> dict:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS parcels,
                AVG(completeness_score) AS completeness_avg,
                AVG(consistency_score) AS consistency_avg,
                AVG(ownership_confidence) AS ownership_avg
            FROM parcel_verifications
            WHERE run_id = ?
            """,
            (self.run_id,),
        ).fetchone()
        flag_row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM verification_flags WHERE run_id = ? AND severity IN ('warn','error')",
            (self.run_id,),
        ).fetchone()
        return {
            "parcels": row["parcels"] or 0,
            "completeness_avg": row["completeness_avg"],
            "consistency_avg": row["consistency_avg"],
            "ownership_avg": row["ownership_avg"],
            "flags_open": flag_row["n"] or 0,
        }

    def _compute_averages(self) -> tuple[float | None, float | None, float | None]:
        row = self._conn.execute(
            """
            SELECT AVG(completeness_score), AVG(consistency_score), AVG(ownership_confidence)
            FROM parcel_verifications
            WHERE run_id = ?
            """,
            (self.run_id,),
        ).fetchone()
        return (row[0], row[1], row[2])
