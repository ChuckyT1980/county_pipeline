Set-Location -Path "C:\Users\chuck\Downloads\county_pipeline"

Write-Host "Creating the 5,000 parcel chunk..."
python -u tax_pipeline/chunk_shasta.py
if ($LASTEXITCODE -ne 0) { throw "Chunking failed" }

Write-Host "Running Stage 2: Verify on Shasta Chunk"
python -u -m tax_pipeline.stage2_verify shasta tax_pipeline/shasta_chunk_5000.csv
if ($LASTEXITCODE -ne 0) { throw "Stage 2 failed" }

Write-Host "Finding latest CRM CSV for Stage 4"
$crm_csv = Get-ChildItem -Filter shasta_crm_*.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $crm_csv) { throw "Could not find CRM CSV" }

Write-Host "Running Stage 4: Owner Enrich on $($crm_csv.Name)"
python -u -m tax_pipeline.stage4_owner_enrich $crm_csv.Name
if ($LASTEXITCODE -ne 0) { throw "Stage 4 failed" }

$enriched_csv = $crm_csv.Name.Replace(".csv", "_enriched.csv")
if (-not (Test-Path $enriched_csv)) { throw "Could not find enriched CSV" }

Write-Host "Copying enriched CSV to MASTER_leads_with_liens.csv for Stage 7"
Copy-Item -Path $enriched_csv -Destination "shasta_MASTER_leads_with_liens.csv" -Force

Write-Host "Running Stage 7: Recorder Enrich"
python -u -m tax_pipeline.stage7_recorder_enrich shasta
if ($LASTEXITCODE -ne 0) { throw "Stage 7 failed" }

Write-Host "Shasta chunk fully processed!"
