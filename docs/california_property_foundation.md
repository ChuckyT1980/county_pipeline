# California Property Foundation

Phase one of a statewide parcel foundation for county_pipeline. This
document describes the model, why it exists, and what it does and does
not change yet.

## Why this exists

Kern's pipeline was found (2026-08-08) silently conflating two different
identifiers into one `apn` field: the **ATN** (Assessment/Tax Number,
Kern's own tax-roll identifier, 5-segment format e.g.
`017-490-06-00-3`) and the **assessor's own parcel number** (a shorter
form, e.g. `017-490-06`). `kern/kern_enrich_docnum_verified.py`
normalized both through the same digits-only string comparison
(`norm()`) and displayed whichever matched as `**APN**` in every one of
the 245 Kern dossiers. The underlying assessor+recorder verification is
real and both-sites-proven - the label on top of it was wrong.

A second real gap found during the same investigation: existing Kern
dossiers state `PRIORITY SIGNAL: GOING TO AUCTION in N days` as a
confirmed claim, but the underlying source
(`kern_REAL_AUCTION_PARCELS_CLEAN.csv`) is a historical snapshot, never
confirmed to be the live, current auction roster. Being on a
Power-to-Sell-style historical list is not the same as being confirmed
on the actual upcoming sale.

Both gaps share a root cause: the pipeline has no place to represent
"this is a real value from a real source, but it means something
narrower/different than the label implies." The model below exists to
give every fact that place.

## The model

Three types, defined in `property_model.py`:

### `Property`

One row per real California parcel - the durable anchor. `ca_property_id`
should almost never change once assigned. Built from the assessor's own
parcel number digits, not the ATN - a county's tax-system bookkeeping
suffix (Kern's trailing `-00-9`) is not part of a parcel's identity.

### `PropertyIdentifier`

One row per `(property, identifier_type, source)`. A property normally
has *multiple* rows here: an `atn` from the tax roll, a separate
`assessor_parcel_number` from the assessor's own page, maybe a
`prior_apn` from before a lot split. **Never merge these into one field**
- that merge is exactly what caused the Kern bug. Each row also carries
`confidence` (`confirmed` / `carried_forward` / `source_list_only` /
`unconfirmed`) so a value read live today is never presented the same
way as a value copied from a historical CSV three months ago.

### `CountySourceConfig`

One per county, loaded from `config/counties/*.yaml`. Declares real
endpoints and separates `tax_default_source` from `auction_source` as
two distinct fields on purpose - a parcel can be tax-default without
being on a confirmed current auction list, or vice versa if redeemed
after listing. `adapter_status` tracks how far a county's real,
live-tested pipeline actually goes (`not_started` /
`recorder_probe_only` / `partial` / `both_sites_verified` / `blocked`).

## What this phase does NOT do

- Does not touch any existing Kern or Butte dossier output.
- Does not build a statewide scraper.
- Does not begin sourcing a statewide parcel index.
- Does not assert that Kern's `Minimum_Bid_Owed` figure is wrong - CA
  R&T Code actually defines minimum bid as the total redemption amount
  (taxes + penalties + costs owed), so "minimum bid" and "amount owed"
  may legitimately be the same number for a tax sale. What the model
  does is give `taxes_owed` and `official_minimum_bid` room to be
  tracked as distinguishable concepts *if* a county source ever states
  them separately - it does not retroactively relabel Kern's existing
  figure without a live source confirming which one it actually is.

## Phase-one milestone

Convert 10 real Kern records and 10 real Butte records into this model,
compare the results, fix anything that only worked for Kern, and produce
a county-readiness checklist. Done when it's true that Kern and Butte
use different county sources, but both resolve into the same California
property model. See `docs/kern_butte_migration_test.md` for the actual
10+10 conversion and comparison, and
`docs/county_readiness_checklist.md` for the resulting checklist.
