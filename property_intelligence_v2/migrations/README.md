# migrations/

The controlled importer, once authorized:

```
legacy Kern / Butte / Lake evidence
  → raw_evidence records
  → observations
  → parcel matches
  → canonical property state
```

Not yet populated. This is explicitly future work - no import/migration
code exists yet, and none will run against real legacy data until
separately authorized. When built, it must read legacy evidence files
read-only and write only into v2's own canonical store - never back into
any legacy county folder, dossier, monitor, dashboard, export, or output.
See the top-level `property_intelligence_v2/README.md` for the full
isolation rule.
