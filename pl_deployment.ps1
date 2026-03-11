# AFG Estimate Analyser - End-to-End Deployment Script
# This script starts all services for the AFG Estimate Analyser project.

$rootDir = Get-Location
$venvPath = Join-Path $rootDir "venv"
$uiDir = Join-Path $rootDir "ui"

Write-Host "--- Stopping existing jobs and orphaned processes ---" -ForegroundColor Cyan
Get-Job | Remove-Job -Force 2>$null
taskkill /F /IM python.exe /T 2>$null
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

# 3. Environment Variables & .env Cleanup
$envPath = Join-Path $rootDir ".env"
if (Test-Path $envPath) {
    Write-Host "Auto-updating .env with local project paths..." -ForegroundColor Yellow
    $content = Get-Content $envPath
    # Clean up absolute paths to match current root
    $content = $content -replace '(?m)^PROJECT_ROOT=.*', "PROJECT_ROOT=$rootDir"
    $content = $content -replace '(?m)^EXTRACTOR_ROOT=.*', "EXTRACTOR_ROOT=$(Join-Path $rootDir 'ExtractorTool')"
    $content = $content -replace '(?m)^MSAF_ROOT=.*', "MSAF_ROOT=$(Join-Path $rootDir 'MSAF')"
    $content = $content -replace '(?m)^EXTRACTION_CONFIG_PATH=.*', "EXTRACTION_CONFIG_PATH=$(Join-Path $rootDir 'ExtractorTool\extraction_config.json')"
    $content | Set-Content $envPath
}

# Values for background jobs
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
    foreach ($key in $env.Keys) { Set-Item "Env:$key" $env[$key] }
    cd $root
    .\venv\Scripts\python.exe ExtractorTool\utils\extraction_service.py
} -ArgumentList $rootDir, $envVars

# 5. Start MSAF Standalone API (Background Job)
Write-Host "Starting Standalone MSAF API on http://localhost:2357..." -ForegroundColor Green
Start-Job -Name "MSAF_API" -ScriptBlock {
    param($root, $env)
    foreach ($key in $env.Keys) { Set-Item "Env:$key" $env[$key] }
    cd $root
    .\venv\Scripts\python.exe MSAF/main.py
} -ArgumentList $rootDir, $envVars

# 6. Start Official Microsoft Agent Framework DevUI
Write-Host "Starting Official DevUI (agent-framework devui)..." -ForegroundColor Green
Start-Job -Name "DevUI" -ScriptBlock {
    param($root, $env)
    foreach ($key in $env.Keys) { Set-Item "Env:$key" $env[$key] }
    cd $root
    .\venv\Scripts\devui.exe MSAF --port 5000
} -ArgumentList $rootDir, $envVars

Write-Host "`n--- All services have been started in the background ---" -ForegroundColor Cyan
Write-Host "Opening live log windows..." -ForegroundColor Yellow

# Start Log Follower Windows

Write-Host "Use 'Get-Job' to see the status of background processes in this window."
Write-Host "To stop all services, run: Get-Job | Stop-Job"
