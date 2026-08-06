# Shasta County Pipeline — Complete

## Status: All 98 Leads Ready

Shasta enrichment is **complete** using the ParcelAssesseeSitus FeatureServer endpoint instead of Stage 7 (Playwright recorder — blocked by DNS resolution).

### What Was Done

| Step | Method | Result |
|------|--------|--------|
| Gating | `shasta_pipeline.py` | 93 passed, 5 skip trace (no address + no assessed value) |
| Address/Owner/Deed | `shasta_feature_server_adapter.py` | 98/98 found via FeatureServer |
| Export tiers | `shasta_pipeline.py` | 4 Tier A, 32 Tier B, 57 Tier C |

### Output Files

| File | Rows | Contents |
|------|------|----------|
| `shasta_tierA.csv` | 4 | Premium: GOLDEN YEARS LLC ($26K), TRUENORTH INC ($22K), SANCHEZ RAMIRO ($16K), MULLINS DAVID F ($8K) |
| `shasta_tierB.csv` | 32 | Moderate distress, $4.8K-$6.8K, all with rec_doc_number |
| `shasta_enriched.csv` | 93 | All gated leads with motivation + Export_Tier |
| `shasta_skiptrace_queue.csv` | 5 | Uncontactable (no address + no assessed value) |
| `shasta_fs_enriched.csv` | 98 | Raw FeatureServer results for all Shasta |

### Master CSV Updates

`northern_ca_MASTER_merged.csv` now has:
- **rec_doc_number: 98/98** Shasta (was 0/98)
- **situs_address: 91/98** Shasta (was 86/98, filled from FS)
- **acres: 97/98** Shasta (was 93/98)
- New fields: `fs_doc_number`, `fs_deed_date`, `fs_situs`, `fs_assessee`, `fs_recorded_acres`, `fs_gis_acres`, `fs_tra`, `fs_assr_link`, `fs_tax_link`

### How ShastaAddressOwnerAdapter Works

Endpoint: `https://gis.shastacounty.gov/arcgis/rest/services/OpenData/ParcelAssesseeSitus/FeatureServer/0/query`

Query by ASMT (12-digit APN without dashes):
```
?where=ASMT='070050072000'
&outFields=APN,ASMT,APN_Dash,Situs_Address,Assessee,Assessee_Address,Current_Doc_Num,Current_Doc_Date,Recorded_Acres,GIS_Acres,TRA,Assr_Link,Tax_Link
&returnGeometry=false
&f=json
```

Returns deterministic JSON, no browser needed. MaxRecordCount: 2000.

### Tier Rule

Tier A: delinquent, balance >= $7.5K, current ownership, has rec_doc_number, has address, has assessed value, not skip trace.
Tier B: delinquent, balance >= $3K but < $7.5K, current ownership, has address, has assessed value, not skip trace.
Tier C: everything else.

### What's Still Blocked

- **Shasta recorder portal** (`recorderselfservice.shastacounty.gov`) — DNS doesn't resolve from this network
  - The FeatureServer provides `Current_Doc_Num`/`Current_Doc_Date` as a substitute
  - Real recorder detail (liens, deed chains) needs Stage 7 from a network that can reach Shasta
- **Phone numbers** — no skip-trace in the pipeline (0/198 across both counties)

### Commands

```bash
# Re-run Shasta enrichment (after master CSV updates):
python tax_pipeline/shasta_feature_server_adapter.py
python shasta_pipeline.py

# Run Tehama sweeper (remove :3 limit is applied):
python tehama_sweeper.py

# Dashboard:
streamlit run dashboard.py
```
