# County Readiness Checklist

Derived from the Kern + Butte migration test (`docs/kern_butte_migration_test.md`).
Use this before treating any county's data as ready to migrate into the
California Property model - each item exists because it either broke
during the Kern/Butte test or was a real difference between the two.

## Identifier discovery

- [ ] Has every distinct identifier type this county's sources actually produce been enumerated? (Kern needed `atn` + `assessor_parcel_number` as two separate values; Butte needed only `assessor_parcel_number`. Do not assume a new county matches either pattern - check its real source columns.)
- [ ] If a county has two numeric/dashed identifiers that LOOK similar, has it been confirmed whether they are the same value in two formats, or genuinely two different identifiers (ATN vs APN)? Do not assume "looks similar" means "same thing."
- [ ] If deriving one identifier from another (e.g. Kern's assessor_parcel_number from its ATN), has the derivation been checked against an independent second source, not just internal consistency? (The Kern migration's first attempt was internally consistent - parsed cleanly, no exceptions thrown - and still wrong, because it silently lost a leading zero. A clean run is not proof of correctness.)
- [ ] Has any identifier stored as a numeric/float type been checked for leading-zero loss? (Kern's `APN_1` column silently dropped a leading zero via CSV/Excel numeric round-tripping - `017490 06` became `1749006.0`. Any identifier that can legitimately start with `0` is at risk of this if it was ever stored numerically rather than as a string.)

## Source separation

- [ ] Are `tax_default_source` and `auction_source` genuinely two different real sources for this county, or the same source serving both roles? State it explicitly either way - don't leave it implicit.
- [ ] If the county's auction list is a historical/snapshot file rather than a live, current listing, is that stated in `refresh_cadence` and reflected in `confidence` (should not be `confirmed` for a value only established from a snapshot)?
- [ ] Does being on a Power-to-Sell / tax-default list get correctly distinguished from being confirmed on the CURRENT, live auction roster? (Kern's existing 245 dossiers state "GOING TO AUCTION in N days" from a historical snapshot never confirmed against the live Sept 2026 list - this is the exact gap this checklist item exists to catch before it happens again in a new county.)

## Confidence levels

- [ ] Does every identifier/value carry an honest `confidence` (`confirmed` / `carried_forward` / `source_list_only` / `unconfirmed`), not a blanket "verified"? (Butte's recorder_document_number values are real but from a prior session - correctly `carried_forward`, not `confirmed`, until re-tested live.)
- [ ] Has "verified" ever been used to mean "present in a CSV" rather than "independently confirmed against a live source"? If so, downgrade to `source_list_only`.

## Recorder capability (per the taxonomy already in use for new-county dispatch)

- [ ] Classified as one of: `RECORDER_FULL` / `RECORDER_INDEX_ONLY` / `RECORDER_MANUAL_ONLY` / `RECORDER_BLOCKED` / `RECORDER_UNKNOWN`?
- [ ] If `RECORDER_INDEX_ONLY`, are downstream dossiers clearly labeled as partial/index-only verification, not silently presented as full both-sites verification?
- [ ] Was the recorder probe tested WITHOUT attempting to bypass any CAPTCHA, login, or rate limit? (A block must be reported as a block, never worked around.)

## Amount/status terminology

- [ ] Is a "minimum bid" figure confirmed to be the county's own published minimum bid, or is it actually "taxes/penalties owed" under a similar-sounding column name? (Under CA R&T Code these can legitimately be the same number for a tax sale - the point is to know which one a given county's source actually states, not to assume.)
- [ ] Does the dossier template avoid stating an auction date/window as confirmed for a SPECIFIC parcel unless that parcel appears on the actual current, live-published list - not just a historical or generic county-wide auction date?

## Before declaring `adapter_status: both_sites_verified`

- [ ] Assessor: live-tested this session, not carried forward from documentation or a prior session.
- [ ] Recorder: classified `RECORDER_FULL` via a real probe, not assumed from another county's Tyler EagleWeb behavior (Fresno and Tehama's Tyler instances are reCAPTCHA-blocked; Del Norte, Glenn, Kings, and Lake's are not - the same platform does not imply the same outcome).
- [ ] At least one real record's identifier chain (assessor -> recorder cross-match) has been traced end-to-end by a human or a documented automated check, the same way the Del Norte and Kern migration samples were traced in this session - not just asserted from a script's own summary.
