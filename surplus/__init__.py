"""
surplus/ — CA county tax sale excess proceeds recovery.

Scrapes county Treasurer-Tax Collector excess proceeds lists, normalizes
into a workable inventory, skip-traces former owners, and generates
outreach dossiers for surplus recovery contingency work.

Pipeline:
    sources.py       — per-county scrapers (config-driven)
    parsers.py       — PDF + HTML → structured rows
    db.py            — SQLite schema + read/write
    skip_trace.py    — provider-agnostic skip trace with stub adapter
    dossier.py       — per-parcel dossier generator (extends butte/build_dossiers)
    outreach.py      — mail-merge + tracking

Entry points:
    python -m surplus.run scrape           # pull all county lists
    python -m surplus.run trace            # skip trace unresolved leads
    python -m surplus.run dossiers         # generate per-parcel PDFs
    python -m surplus.run summary          # inventory report
"""
