# deploy.ps1
# Helper script to build and deploy the Playwright scraper to Google Cloud Run

$PROJECT_ID = "YOUR_GCP_PROJECT_ID_HERE"
$SERVICE_NAME = "tehama-recorder-enrichment"
$REGION = "us-west1"
$IMAGE = "gcr.io/$PROJECT_ID/$SERVICE_NAME"

Write-Host "Make sure you have authenticated using: gcloud auth login" -ForegroundColor Yellow
Write-Host "Deploying to project: $PROJECT_ID" -ForegroundColor Cyan

# 1. Build the Docker image using Cloud Build
Write-Host "Building Docker image using Cloud Build..." -ForegroundColor Green
gcloud builds submit --tag $IMAGE --project $PROJECT_ID

# 2. Deploy to Cloud Run (IAM secured)
Write-Host "Deploying to Cloud Run (Secured with IAM)..." -ForegroundColor Green
gcloud run deploy $SERVICE_NAME `
  --image $IMAGE `
  --region $REGION `
  --project $PROJECT_ID `
  --platform managed `
  --memory 2Gi `
  --cpu 1 `
  --timeout 120s `
  --no-allow-unauthenticated

Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "To invoke this service from your cron job, you will need a service account with the 'Cloud Run Invoker' role." -ForegroundColor Yellow
