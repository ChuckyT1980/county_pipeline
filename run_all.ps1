$ErrorActionPreference = "Stop"

$county = "shasta"
if ($args.Count -gt 0) {
    $county = $args[0]
}

Write-Host "=============================================="
Write-Host " STARTING FULL PIPELINE FOR $county.ToUpper()"
Write-Host "=============================================="

# 1. Run Discovery and Verification (Stages 1-3)
Write-Host "`n>>> Running Stage 1-3 (Discovery & Verification)..."
# We need to capture the output to find the CRM filename
$output = python tax_pipeline/run_pipeline.py $county
$output | Write-Host

$crm_line = $output | Where-Object { $_ -match "CRM\s+:" }
if (-not $crm_line) {
    Write-Host "Failed to find CRM output file in logs. Exiting."
    exit 1
}
$crm_file = $crm_line -split ":" | Select-Object -Last 1
$crm_file = $crm_file.Trim()

Write-Host "`n>>> Found CRM Leads file: $crm_file"

# 2. Run Owner Enrichment (Stage 4)
Write-Host "`n>>> Running Stage 4 (Owner Enrichment)..."
python tax_pipeline/stage4_owner_enrich.py $crm_file

$enriched_file = $crm_file.Replace(".csv", "_enriched.csv")

if (-not (Test-Path $enriched_file)) {
    Write-Host "Failed to find enriched output file: $enriched_file. Exiting."
    exit 1
}

# 3. Prepare for Stage 7
$master_file = "tax_pipeline/${county}_MASTER_leads.csv"
Write-Host "`n>>> Copying $enriched_file to $master_file for Stage 7..."
Copy-Item $enriched_file $master_file -Force

# 4. Run Recorder Enrichment (Stage 7)
Write-Host "`n>>> Running Stage 7 (Recorder Enrichment)..."
python tax_pipeline/stage7_recorder_enrich.py $county

Write-Host "`n=============================================="
Write-Host " FULL PIPELINE COMPLETE FOR $county.ToUpper()"
Write-Host " The dashboard is now ready to use!"
Write-Host "=============================================="
