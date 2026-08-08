# DOSSIER_QA — Bypass Remediation Round

**Date**: 2026-08-08
**Trigger**: Read-only release-integrity audit found `fetch_butte_task1.py` reachable via a live Streamlit button (`ca_unify_dashboard.py`), bypassing the redemption filter with zero warning.

## What changed

1. **Canonical path established**: `regen_butte_dossiers.run_canonical_generation_captured()` — a thin, Streamlit-free wrapper around the existing `main()` (which already applies `is_redeemed()`). No filtering logic duplicated.
2. **Dashboard button fixed**: `ca_unify_dashboard.py`'s "📋 Generate Butte Dossiers" button now calls `regen_butte_dossiers.run_canonical_generation_captured()` in-process. No `subprocess`, no `fetch_butte_task1` reference except an explanatory historical comment.
3. **`fetch_butte_task1.py` retired fail-closed**: `task1c()` (the only function that ever wrote to `output/dashboard/`) now raises `RuntimeError` unconditionally, whether called via `__main__` or imported and called directly. Running it as a script prints a deprecation message to stderr and exits 1, before any I/O. `task1a()`/`task1b()` (data-gathering only, never wrote to `output/dashboard/`) preserved unchanged as an audit trail, but are unreachable from `__main__`.
4. **A new export/feed gap found and fixed during this round**: `report_builder.py`'s `dashboard_feed.json` serialization for `PROPERTY_INTELLIGENCE` records previously used the *raw, uncorrected* `signal["priority_label"]` and omitted the identifier/equity fields entirely — meaning the feed could still carry "GOING TO AUCTION" even after the rendered `.md` dossier was fixed in commit `27c6cd4`. Fixed to serialize the same corrected values the dossier itself renders.

## Rendered-output integrity checks (all against real, on-disk text — not source strings, not exit codes)

| Check | Scope | Result |
|---|---|---|
| (a) No "Lien Risk Tier" label | 365/365 real dossiers | PASS |
| (b) No bare HIGH/MEDIUM/LOW outside the disclaimed equity line | 365/365 | PASS |
| (c) No "GOING TO AUCTION" | 365/365 | PASS |
| (d) No ATN rendered as bare "APN" | 365/365 | PASS |
| (e) Equity/Assessed-Value Indicator label + disclaimer present | 365/365 | PASS |
| (f.1) Redeemed fixture blocked via canonical generator | temp-dir fixture | PASS |
| (f.2) Redeemed fixture blocked via dashboard wrapper | temp-dir fixture | PASS |
| (f.3) Redeemed fixture blocked via deprecated script (subprocess + direct call) | subprocess + import | PASS |
| Dashboard button resolves to canonical path only | source-level (AST/text) | PASS |
| Repo-wide: no live invocation of `fetch_butte_task1` anywhere tracked | `git grep` | PASS (3 mentions, all deprecation-context comments, 0 live invocations) |
| Export/feed serializes corrected fields | temp-dir functional test | PASS |

## Portfolio integrity

Zero changes to the real 365 dossiers or `dashboard_feed.json` this round (`git diff --stat HEAD -- output/dashboard/` is empty). One accidental live regeneration occurred mid-session (calling the new function without monkeypatching first) and was caught and fully reverted (`git checkout -- output/dashboard/butte_*.md output/dashboard/dashboard_feed.json`) before any further work — confirmed via diff that only `Generated Date` timestamps had changed, no factual fields.

## Known residual gap

The live `dashboard_feed.json`'s existing ~200 rolling entries (generated before this round's export fix) still contain whatever the pre-fix serialization produced for those specific records — this fix only affects *future* generations. Correcting historical feed entries would require re-running generation against the real portfolio, which was out of scope this round ("do not regenerate the portfolio unless a test requires a temporary isolated output directory").
