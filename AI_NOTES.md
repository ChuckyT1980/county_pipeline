# AI Session Notes — County Pipeline

> Last updated: 2026-07-07
> This file exists so a future session can resume context if this one disconnects.

---

## Current Priority Stack
1. **Validate Shasta end-to-end on a small sample** — user wants confidence another county works.
2. **Implement PSL-1** — predictive seller layer design approved (Option 2 signal-layer with feedback loop).
3. **(Deferred)** Wire Lassen and Butte — blocked on free owner data paths.

---

## Python Validation Rule
When editing or creating `.py` files:

```bash
python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" <path>
```

- On `SyntaxError`, fix the root cause with another edit.
- Never paper over by commenting out, wrapping in `try/except`, or skipping the rule.
- Re-validate after each fix.
- Do NOT use `python3 file.py` to validate (runs the file).
- Do NOT use `py_compile` (writes `.pyc` artifacts).

---

## Project Paths

```
/mnt/c/Users/chuck/Downloads/county_pipeline/
├── tax_pipeline/
│   ├── stage1_discover.py
│   ├── stage2_verify.py
│   ├── stage4_owner_enrich.py
│   ├── stage7_recorder_enrich.py
│   ├── config.py
│   ├── recorder_config.py
│   ├── run_pipeline.py
│   └── sample_shasta_run.py   # inline script provided; user may save
├── connectors/
├── cps1_learning.py
├── cps1_weights.json
├── deal_tracker.py
├── all_seller_intent.csv
└── AI_NOTES.md   # this file
```

---

## County Status

| County | Platform | Tax Data | Owner/Mailing | Recorder | Status |
|--------|----------|----------|---------------|----------|--------|
| Tehama | common2.mptsweb.com | Works | Works | Works | **Sellable** — 35 leads ready |
| Shasta | common2.mptsweb.com | Works | Works (MBAP AsrPrint) | EagleWeb/Tyler | **Works**; user wants larger sample run |
| Butte  | common2.mptsweb.com | Works (tax year 2026) | **Blocked** — no free owner source | Blocked without owner | Deferred |
| Lassen | countytaxretriever.com | Search disabled | N/A | N/A | Deferred |

### Butte Free Owner Paths Tried (all blocked)
- MPTS tax portal: no owner field
- Tax bill PDF: no owner/mailing address
- MBAP AsrPrint endpoint: 404
- Regrid free API: requires access token
- ParcelQuest: requires registration/user agreement
- Butte GIS FeatureServer/MapServer: requires login token

### Lassen
- Confirmed **not** on MPTS.
- Uses County Tax Retriever (`countytaxretriever.com`), but search is currently disabled.

---

## PSL-1 — Predictive Seller Layer

- Design approved: **Option 2** (signal-layer predictor with feedback loop).
- Full spec: `/mnt/c/Users/chuck/Downloads/county_pipeline/docs/superpowers/specs/2026-07-07-predictive-seller-layer-design.md`
- Components to build:
  - `signals.py`
  - `predictor.py`
  - `predictor_weights.json`
  - `feedback.py`
  - `predictor_report.py`
- Output columns: `psl1_sell_score`, `psl1_offer_type`, `psl1_timing_bucket`, `psl1_explanation`, `psl1_confidence`

---

## Tehama 35 Leads

- Source dossier: `/mnt/c/Users/chuck/Downloads/tehama_35_dossiers.txt`
- Summary: 35 leads, $35K+ delinquent taxes, 89 liens, 31 rentals, 5 out-of-state
- Buyer rankings: `/home/chuck/.kimchi/docs/tehama_buyer_rankings.txt`
- Sales templates: `/home/chuck/.kimchi/docs/tehama_35_sales_templates.txt`
- Phone script: `/home/chuck/.kimchi/docs/phone_script_today.txt`
- Status: User contacted Oscar at IBuyRedding, sent 2 sample leads

---

## Shasta Next Step

User wants a small sample that passes through all 7 stages. Inline script provided:

```python
# Save as /mnt/c/Users/chuck/Downloads/county_pipeline/tax_pipeline/sample_shasta_run.py
# Run: python sample_shasta_run.py
# Then: python stage2_verify.py shasta shasta_sample_discovery_*.csv
# Then: python stage4_owner_enrich.py shasta_crm_*.csv
# Then: python -m tax_pipeline.stage7_recorder_enrich shasta
```

Full Shasta coverage estimated at 3–6 hours via `python stage1_discover.py shasta` (resumable).

---

## Open Questions

1. PSL-1: distance-to-property from ZIP or omit initially?
2. PSL-1: add "creative financing" offer type?
3. PSL-1: feedback frequency — per batch, weekly, or on demand?
4. PSL-1: county-specific weights or global weights?
5. When will we revisit free owner-enrichment paths for Butte/Lassen?

---

## Constraints

- Business model is **selling data**, not buying it.
- No paid sources (Regrid tokens, ParcelQuest, paid GIS logins) without explicit approval.
- Use existing libraries only: pandas, requests, beautifulsoup4, playwright.
- Pipeline data must come from live county assessor + recorder websites.
- Runtime environment (Linux agent) lacks pandas/playwright/pip; pipeline execution must happen on user's Windows/WSL environment.
