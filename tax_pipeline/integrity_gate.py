"""
integrity_gate.py

Drop-in periodic self-check for the Stage 2 enrichment loop. Instead of
running thousands of records blind and verifying after the fact, this
checks a rolling window of recently-written records every N rows and
halts the pipeline immediately if corruption appears — the same checks
verify_doc_number_integrity.py does, just running live instead of
after-the-fact.

Usage inside your Stage 2 loop (stage2_http.py or wherever the per-record
loop lives):

    from integrity_gate import IntegrityGate

    gate = IntegrityGate(
        check_every=100,
        input_doc_field="doc_fmt",
        county="tehama",
        history_file="tehama_integrity_history.jsonl",
    )

    for i, row in df.iterrows():
        result_row = process_one_record(row)   # your existing logic
        results_list.append(result_row)

        gate.record(result_row)
        if gate.should_check():
            ok, report = gate.check()
            if not ok:
                print(report)
                raise SystemExit(
                    "Integrity gate failed — halting pipeline. "
                    "Fix the bug before resuming, don't let this keep writing."
                )
            else:
                print(f"[integrity_gate] OK at record {i+1} — {report}")

    # ALWAYS call this after the loop ends, regardless of whether the total
    # record count landed on a check_every boundary — otherwise the tail
    # end of every batch silently escapes verification. See finalize()
    # docstring for the confirmed real bug this fixes.
    final = gate.finalize()
    if final is not None:
        ok, report = final
        if not ok:
            print(report)
            raise SystemExit("Integrity gate failed on final tail check.")
        else:
            print(f"[integrity_gate] Final tail check OK — {report}")

    # After investigating and fixing a halt, before restarting the pipeline:
    #   gate.log_resume("fixed X, restarted from checkpoint at record N")

Review any county's full stop/fix/resume history at any time:
    python integrity_gate.py --history tehama_integrity_history.jsonl

Design choices:
  - Fails LOUD by default (raises/exits) rather than logging and continuing,
    because every corruption incident in this pipeline so far was caught
    only by someone manually re-checking after the fact, sometimes hours
    and thousands of records later. A hard stop costs you a restart; a
    silent corruption costs you a full re-verification pass and possibly
    bad leads reaching a buyer.
  - Checks a ROLLING WINDOW (the last `check_every` records), not the
    whole file — keeps each check fast (O(window), not O(total)) so it's
    cheap enough to run every N records without slowing the pipeline down.
  - Checks TWO things, not one: hit_rate (did the client get ANY chain data
    at all in this window?) and corrupt_rate (of the data it got, how much
    is structurally corrupt?). A prior version only checked corrupt_rate,
    which computed 0/0 = 0.0% whenever the client silently produced zero
    chain data for an entire window — passing every check while 20,000
    Tehama/Shasta records ran completely blank due to an expired/missing
    session. hit_rate is checked independently so a total-failure client
    can never hide behind a technically-true 0% corruption rate.
  - Reuses the same corruption shape-check as verify_doc_number_integrity.py
    (digits/R/hyphen only = healthy; letters spread across words or the
    literal string UNKNOWN = structurally corrupt) so the two tools never
    drift out of sync on what "bad" means.
"""

import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DOC_NUMBER_SHAPE_RE = re.compile(r"^[\dR\-]+$")


@dataclass
class IntegrityGate:
    check_every: int = 100
    input_doc_field: str = "doc_fmt"
    corrupt_rate_threshold: float = 0.02   # halt if >2% of chain events are corrupt
    # CALIBRATE THIS, don't trust the default: some parcels legitimately have
    # no recorder hit (malformed source doc numbers, genuinely no filing).
    # 0.30 is a guess. Before relying on this, run a known-good batch and set
    # min_hit_rate a bit below whatever hit rate that batch actually achieves,
    # so a real collapse (session/cookie/endpoint failure) still trips it.
    min_hit_rate: float = 0.30
    county: str = "unknown"
    history_file: str = "integrity_gate_history.jsonl"
    window: deque = field(default_factory=lambda: deque(maxlen=100))
    _since_last_check: int = 0
    _record_index: int = 0

    def __post_init__(self):
        # rebuild the deque with the configured maxlen (dataclass default
        # factory above uses a fixed 100 — this fixes it to check_every)
        self.window = deque(maxlen=self.check_every)
        self._log_event({
            "event": "gate_started",
            "county": self.county,
            "check_every": self.check_every,
            "corrupt_rate_threshold": self.corrupt_rate_threshold,
        })

    def _log_event(self, payload: dict):
        """Append-only audit trail. Every halt, resume, and threshold change
        gets a permanent record — so a long run's stop/fix/resume cycles
        can be reviewed after the fact instead of trusted on faith."""
        entry = {"timestamp": time.time(), "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S"), **payload}
        with open(self.history_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def set_threshold(self, new_threshold: float, reason: str):
        """Use this instead of setting corrupt_rate_threshold directly.
        Forces a written justification for every threshold change, logged
        separately from bug-fix events, so 'raised the threshold to make
        the alert go away' is visible in the audit trail as exactly that."""
        old = self.corrupt_rate_threshold
        self.corrupt_rate_threshold = new_threshold
        self._log_event({
            "event": "threshold_changed",
            "county": self.county,
            "old_threshold": old,
            "new_threshold": new_threshold,
            "reason": reason,
        })

    def record(self, result_row: dict):
        """Call once per processed record, after it's built but before/as
        it's appended to your results list."""
        self.window.append(result_row)
        self._since_last_check += 1
        self._record_index += 1

    def should_check(self) -> bool:
        return self._since_last_check >= self.check_every

    def check(self) -> tuple[bool, str]:
        """Runs the integrity check against the current window and resets
        the counter. Returns (passed, human_readable_report). Every check
        — pass or fail — is written to the history file.

        Checks TWO independent things, because they fail for different
        reasons and one masking the other is exactly how 20,000 blank
        Tehama/Shasta records slipped through undetected:
          1. hit_rate: of the rows in this window, what fraction produced
             ANY recorder_chain data at all? A collapsed hit rate (session
             expired, disclaimer cookie missing, endpoint silently 500ing
             into a caught exception) means the client stopped working —
             completely independent of whether any given chain is 'clean'.
          2. corrupt_rate: of the chain EVENTS that did get produced, what
             fraction are structurally corrupt (names/UNKNOWN in doc_number
             fields)? This only means something once hit_rate confirms
             there's real data to judge in the first place.
        A 0/0 corrupt_rate is NOT treated as passing — it's only reachable
        when hit_rate is also checked, and a hit_rate of 0 fails on its own.
        """
        self._since_last_check = 0

        total_events = 0
        empty_events = 0
        corrupt_events = 0
        corrupt_examples = []
        rows_with_any_chain = 0

        for row in self.window:
            chain_raw = row.get("recorder_chain")
            if not chain_raw:
                continue
            try:
                chain = json.loads(chain_raw) if isinstance(chain_raw, str) else chain_raw
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not chain:
                continue

            rows_with_any_chain += 1
            input_doc = str(row.get(self.input_doc_field, "")).strip()

            for event in chain:
                total_events += 1
                doc_num = str(event.get("doc_number", "")).strip()

                if not doc_num:
                    empty_events += 1
                    continue

                if not DOC_NUMBER_SHAPE_RE.match(doc_num):
                    corrupt_events += 1
                    if len(corrupt_examples) < 5:
                        corrupt_examples.append(
                            f"input={input_doc!r} bad_doc_number={doc_num!r}"
                        )

        window_size = len(self.window)
        hit_rate = (rows_with_any_chain / window_size) if window_size else 0.0
        corrupt_rate = (corrupt_events / total_events) if total_events else 0.0

        hit_rate_ok = hit_rate >= self.min_hit_rate
        corrupt_rate_ok = corrupt_rate <= self.corrupt_rate_threshold
        passed = hit_rate_ok and corrupt_rate_ok

        report_lines = [
            f"window_size={window_size} rows_with_chain={rows_with_any_chain} "
            f"hit_rate={hit_rate:.1%} (min {self.min_hit_rate:.1%}) "
            f"total_chain_events={total_events} empty={empty_events} corrupt={corrupt_events} "
            f"corrupt_rate={corrupt_rate:.1%} (max {self.corrupt_rate_threshold:.1%})"
        ]
        if not hit_rate_ok:
            report_lines.append(
                "*** HIT RATE COLLAPSED — client is likely silently failing "
                "(expired session, missing disclaimer cookie, endpoint erroring "
                "into a caught exception) — check the actual HTTP responses, "
                "don't assume the corruption check alone means the run is healthy."
            )
        if corrupt_examples:
            report_lines.append("Corrupt examples: " + " | ".join(corrupt_examples))

        self._log_event({
            "event": "check_passed" if passed else "check_FAILED",
            "county": self.county,
            "record_index": self._record_index,
            "window_size": window_size,
            "rows_with_chain": rows_with_any_chain,
            "hit_rate": hit_rate,
            "min_hit_rate": self.min_hit_rate,
            "hit_rate_ok": hit_rate_ok,
            "total_chain_events": total_events,
            "empty_events": empty_events,
            "corrupt_events": corrupt_events,
            "corrupt_rate": corrupt_rate,
            "corrupt_rate_threshold": self.corrupt_rate_threshold,
            "corrupt_rate_ok": corrupt_rate_ok,
            "corrupt_examples": corrupt_examples,
        })

        return passed, "\n".join(report_lines)

    def finalize(self) -> Optional[tuple]:
        """Call this ONCE, after your processing loop ends, regardless of
        whether the loop's total record count landed on a check_every
        boundary. Confirmed real gap (7/14): a 75-row Butte batch with
        check_every=50 only ever checked the first 50 records — rows 51-75
        ran through the loop but were never verified by the gate at all,
        since the loop ended before reaching the next 50-multiple. Any
        batch whose size isn't a clean multiple of check_every has this
        same silent tail-end gap. finalize() forces one last check on
        whatever's left in the window, so every record gets verified
        exactly once before the pipeline is considered done.

        Returns None if there was nothing new to check (window already
        checked and empty since), otherwise the same (passed, report)
        tuple that check() returns.

        Usage — add this line right after your processing loop, before
        declaring the run complete:

            for i, row in df.iterrows():
                ...
                gate.record(result_row)
                if gate.should_check():
                    ok, report = gate.check()
                    ...

            final = gate.finalize()
            if final is not None:
                ok, report = final
                if not ok:
                    print(report)
                    raise SystemExit("Integrity gate failed on final tail check.")
                else:
                    print(f"[integrity_gate] Final tail check OK\n{report}")
        """
        if self._since_last_check == 0:
            return None  # nothing unverified since the last check
        return self.check()

    def log_resume(self, note: str):
        """Call this explicitly after fixing a bug and resuming the pipeline
        following a halt, so the audit trail shows not just 'it stopped' but
        'here's what was done about it and when it resumed'."""
        self._log_event({
            "event": "resumed",
            "county": self.county,
            "record_index": self._record_index,
            "note": note,
        })


def print_history(history_file: str = "integrity_gate_history.jsonl"):
    """Human-readable summary of a county's stop/fix/resume audit trail.
    Run standalone: python integrity_gate.py --history [path]"""
    path = Path(history_file)
    if not path.exists():
        print(f"No history file at {history_file} yet.")
        return

    with open(path) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    for entry in lines:
        ts = entry.get("timestamp_iso", "?")
        event = entry.get("event", "?")
        county = entry.get("county", "?")

        if event == "gate_started":
            print(f"{ts} [{county}] GATE STARTED  check_every={entry['check_every']} "
                  f"threshold={entry['corrupt_rate_threshold']:.1%}")
        elif event == "check_FAILED":
            reasons = []
            if not entry.get("hit_rate_ok", True):
                reasons.append(f"HIT RATE {entry.get('hit_rate', 0):.1%} < min {entry.get('min_hit_rate', 0):.1%}")
            if not entry.get("corrupt_rate_ok", True):
                reasons.append(f"CORRUPT RATE {entry.get('corrupt_rate', 0):.1%} > max {entry.get('corrupt_rate_threshold', 0):.1%}")
            print(f"{ts} [{county}] *** HALT ***  record #{entry['record_index']}  {' AND '.join(reasons)}")
            for ex in entry.get("corrupt_examples", []):
                print(f"           {ex}")
        elif event == "check_passed":
            print(f"{ts} [{county}] ok  record #{entry['record_index']}  "
                  f"hit_rate={entry.get('hit_rate', 0):.1%} corrupt_rate={entry.get('corrupt_rate', 0):.1%}")
        elif event == "resumed":
            print(f"{ts} [{county}] RESUMED  record #{entry['record_index']}  note={entry.get('note', '')!r}")
        elif event == "threshold_changed":
            print(f"{ts} [{county}] THRESHOLD CHANGED  {entry['old_threshold']:.1%} -> "
                  f"{entry['new_threshold']:.1%}  reason={entry.get('reason', '')!r}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--history":
        hist_path = sys.argv[2] if len(sys.argv) > 2 else "integrity_gate_history.jsonl"
        print_history(hist_path)
        raise SystemExit(0)

    # Quick self-test with synthetic rows
    import os
    test_history = "test_integrity_gate_history.jsonl"
    if os.path.exists(test_history):
        os.remove(test_history)

    gate = IntegrityGate(check_every=5, input_doc_field="doc_fmt", county="test", history_file=test_history)

    good_rows = [
        {"doc_fmt": "2013006445", "recorder_chain": json.dumps([{"doc_number": "2013006445"}])}
        for _ in range(4)
    ]
    bad_row = {
        "doc_fmt": "2025-0009681",
        "recorder_chain": json.dumps([{"doc_number": "2025-0009681"}, {"doc_number": "REYNOLDS DONALD R"}]),
    }

    for row in good_rows + [bad_row]:
        gate.record(row)
        if gate.should_check():
            ok, report = gate.check()
            print(f"PASSED={ok}\n{report}")

    gate.log_resume("fixed name-parsing bug in _parse_results_html, restarted from checkpoint")

    print("\n--- Regression test: the exact Tehama/Shasta blind spot ---")
    print("(a window of NOTHING but empty chains must now FAIL, not pass as 0/0)")
    gate2 = IntegrityGate(check_every=5, input_doc_field="doc_fmt", county="test-blind-spot", history_file=test_history)
    all_empty_rows = [
        {"doc_fmt": "2020R0035761", "recorder_chain": json.dumps([])}
        for _ in range(5)
    ]
    for row in all_empty_rows:
        gate2.record(row)
        if gate2.should_check():
            ok, report = gate2.check()
            print(f"PASSED={ok}\n{report}")
            assert ok is False, "REGRESSION: all-empty-chain window must fail the hit-rate check"
    print("Confirmed: all-empty window correctly FAILS instead of silently passing.")

    print("\n--- History file contents ---")
    print_history(test_history)
    os.remove(test_history)
