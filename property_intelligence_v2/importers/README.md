# importers/

`legacy_evidence_importer.py` - the controlled importer: one legacy
evidence file (Kern / Butte / Lake / Del Norte only) -> `raw_evidence` +
`evidence_disposition` + `observations`, written transactionally into
property_intelligence_v2's own store. Reads legacy files read-only; never
writes back into any legacy county folder, dossier, monitor, dashboard,
export, or output - see the top-level `property_intelligence_v2/README.md`
isolation rule.

Scope, stated honestly: this module does not parse or extract fields from
legacy documents. Callers supply already-extracted observation fields; the
importer's own job is narrower - validate the input path against the
manifest, validate the artifact root, hash and content-address-store the
file, and persist records transactionally with the required
disposition-before-observations ordering and identity-uniqueness
enforcement. It has been tested against synthetic fixtures only (see
`tests/test_legacy_evidence_importer.py`) and has not been run against
real legacy county evidence.

Configuration is exclusively through the `PIV2_ARTIFACT_ROOT` environment
variable - an absolute path outside the repository. See the module's own
docstring for the full evidence-identity decision, concurrency mechanism,
failure/orphan-artifact audit-trail design, and importer write boundary.
