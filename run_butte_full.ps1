Set-Location -Path "C:\Users\chuck\Downloads\county_pipeline"

Write-Host "Running Stage 2: Verify"
python -u -m tax_pipeline.stage2_verify butte tax_pipeline/butte_15_percent_sample.csv
if ($LASTEXITCODE -ne 0) { throw "Stage 2 failed" }

Write-Host "Finding latest CRM CSV for Stage 4"
$crm_csv = Get-ChildItem -Filter butte_crm_*.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $crm_csv) { throw "Could not find CRM CSV" }

Write-Host "Running Stage 4: Owner Enrich on $($crm_csv.Name)"
python -u -m tax_pipeline.stage4_owner_enrich $crm_csv.Name
if ($LASTEXITCODE -ne 0) { throw "Stage 4 failed" }

$enriched_csv = $crm_csv.Name.Replace(".csv", "_enriched.csv")
if (-not (Test-Path $enriched_csv)) { throw "Could not find enriched CSV" }

Write-Host "Copying enriched CSV to MASTER_leads_with_liens.csv for Stage 7"
Copy-Item -Path $enriched_csv -Destination "butte_MASTER_leads_with_liens.csv" -Force

Write-Host "Running Stage 7: Recorder Enrich"
python -u -m tax_pipeline.stage7_recorder_enrich butte
if ($LASTEXITCODE -ne 0) { throw "Stage 7 failed" }

Write-Host "All stages completed successfully."
