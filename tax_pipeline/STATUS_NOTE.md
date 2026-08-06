# Current Pipeline Status & Next Steps

## 1. Tax Pipeline (MPTS)
- **Generic Adapter Built**: We built `test_discovery_mpts.py` which dynamically discovers parcels for any MPTS county using the configuration file.
- **Config Updated**: `config.py` now includes endpoints for `tehama`, `shasta`, `glenn`, `colusa`, `plumas`, `lassen`, `siskiyou`, `trinity`, and `modoc`.
- **Tested & Verified**: We successfully pulled test discovery data for Colusa (90 parcels) and Butte (3107 parcels). Glenn returned 0 parcels, likely because the specific book used for the test was empty.

## 2. Recorder Pipeline (EagleWeb)
- **Registry Created**: We created `recorder_config.py` to handle the differences between various EagleWeb county implementations.
- **Lassen Debugged**: We found that Lassen uses an older/different EagleWeb layout that requires a guest login URL (`loginPOST.jsp?guest=true`) to bypass the disclaimer entirely, and its search input is `#BothNamesIDSearchString`. We mapped these quirks into `recorder_config.py`.

## Next Step Upon Return
The immediate next step is to update `stage7_recorder_enrich.py` so that it imports and uses the new `RECORDER_CONFIG` from `recorder_config.py` instead of its hardcoded logic. This will allow the single script to adapt its DOM selectors and navigation flow seamlessly across Tehama, Shasta, and Lassen.

- **And Butte**: We will also investigate and integrate Butte's recorder portal (CivicPlus) when we resume.
