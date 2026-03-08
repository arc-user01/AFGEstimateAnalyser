# AFG Estimate Analyser - End-to-End Deployment Script
# This script starts all services for the AFG Estimate Analyser project.

$rootDir = Get-Location
$venvPath = Join-Path $rootDir "venv"
$uiDir = Join-Path $rootDir "ui"

Write-Host "--- Stopping existing jobs and orphaned processes ---" -ForegroundColor Cyan
Get-Job | Remove-Job -Force 2>$null
taskkill /F /IM python.exe /T 2>$null
taskkill /F /IM celery.exe /T 2>$null
taskkill /F /IM node.exe /T 2>$null

Write-Host "`n--- Starting AFG Estimate Analyser Deployment ---" -ForegroundColor Cyan
# 1. Virtual Environment Setup
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "Activating venv and installing requirements..." -ForegroundColor Yellow
& "$venvPath\Scripts\pip.exe" install -r requirements.txt --pre

# 2. UI Dependencies
if (-not (Test-Path (Join-Path $uiDir "node_modules"))) {
    Write-Host "Installing UI dependencies (npm install)..." -ForegroundColor Yellow
    Push-Location $uiDir
    npm install
    Pop-Location
}

# 3. Environment Variables Setup (for Jobs)
# We will pass these to the background jobs
$envVars = @{
    "PYTHONPATH" = $rootDir
    "PROJECT_ROOT" = $rootDir
    "EXTRACTOR_ROOT" = Join-Path $rootDir "ExtractorTool"
    "EXTRACTION_SERVICE_URL" = "http://localhost:1204"
}

# 4. Start Extraction Service (Background Job)
Write-Host "Starting Extraction Service on http://localhost:1204..." -ForegroundColor Green
Start-Job -Name "ExtractionService" -ScriptBlock {
    param($root, $env)
    $env.Keys | ForEach-Object { [System.Environment]::SetEnvironmentVariable($_, $env[$_]) }
    cd $root
    .\venv\Scripts\python.exe ExtractorTool\extraction_service.py
} -ArgumentList $rootDir, $envVars

# 5. Start Celery Worker (Background Job)
Write-Host "Starting Celery Worker (MSAF)..." -ForegroundColor Green
Start-Job -Name "CeleryWorker" -ScriptBlock {
    param($root, $env)
    $env.Keys | ForEach-Object { [System.Environment]::SetEnvironmentVariable($_, $env[$_]) }
    cd $root
    .\venv\Scripts\celery.exe -A MSAF.worker worker --loglevel=info -P threads --concurrency=10
} -ArgumentList $rootDir, $envVars

# 6. Start Backend API (Background Job)
Write-Host "Starting Backend API on http://localhost:2357..." -ForegroundColor Green
Start-Job -Name "BackendAPI" -ScriptBlock {
    param($root, $env)
    $env.Keys | ForEach-Object { [System.Environment]::SetEnvironmentVariable($_, $env[$_]) }
    cd $root
    .\venv\Scripts\python.exe agent_backend\main.py
} -ArgumentList $rootDir, $envVars

# 7. Start Frontend UI
Write-Host "Starting Frontend UI (npm run dev)..." -ForegroundColor Green
Start-Job -Name "FrontendUI" -ScriptBlock {
    param($ui)
    cd $ui
    npm run dev
} -ArgumentList $uiDir

Write-Host "`n--- All services have been started in the background ---" -ForegroundColor Cyan
Write-Host "Use 'Get-Job' to see the status of background processes."
Write-Host "Use 'Receive-Job -Name <Name> -Keep' to see output logs."
Write-Host "To stop all services, run: Get-Job | Stop-Job"
