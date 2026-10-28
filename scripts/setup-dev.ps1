<#
.SYNOPSIS
    setup-dev.ps1 — Automated Developer Workstation Setup Script.
.DESCRIPTION
    Initializes Python virtual environment, installs backend dependencies,
    provisions frontend dependencies, and prepares local environment configuration.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  GEC Student Database ERP — Developer Workstation Setup      " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Root: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Step 1: Pre-flight environment check
$checkScript = Join-Path $ScriptRoot "check-environment.ps1"
if (Test-Path $checkScript) {
    & $checkScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Pre-flight environment audit failed. Resolve required tools before continuing."
        exit 1
    }
}

# Step 2: Set up Python virtual environment
Write-Host ""
Write-Host "[Step 1/4] Configuring Python Virtual Environment in backend\.venv..." -ForegroundColor Yellow
$backendDir = Join-Path $ProjectRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment at $venvDir..." -ForegroundColor Gray
    & python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create Python virtual environment."
        exit 1
    }
} else {
    Write-Host "Virtual environment already exists at $venvDir." -ForegroundColor Green
}

# Step 3: Install backend dependencies
Write-Host ""
Write-Host "[Step 2/4] Installing Python dependencies from backend\requirements.txt..." -ForegroundColor Yellow
$reqFile = Join-Path $backendDir "requirements.txt"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed for backend\requirements.txt."
    exit 1
}
Write-Host "Python dependencies installed successfully." -ForegroundColor Green

# Step 4: Provision backend .env from template if missing
Write-Host ""
Write-Host "[Step 3/4] Checking backend environment configuration..." -ForegroundColor Yellow
$envFile = Join-Path $backendDir ".env"
$envTemplate = Join-Path $backendDir ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envTemplate) {
        Copy-Item -Path $envTemplate -Destination $envFile
        Write-Host "Copied backend\.env.example -> backend\.env." -ForegroundColor Green
        Write-Host "IMPORTANT: Open backend\.env and configure your MySQL password and SECRET_KEY." -ForegroundColor Yellow
    } else {
        Write-Error "Template backend\.env.example is missing."
        exit 1
    }
} else {
    Write-Host "backend\.env already exists. Preserving existing configuration." -ForegroundColor Green
}

# Step 5: Install frontend dependencies
Write-Host ""
Write-Host "[Step 4/4] Installing frontend dependencies..." -ForegroundColor Yellow
$frontendDir = Join-Path $ProjectRoot "frontend"
Push-Location $frontendDir
try {
    if (Test-Path "package-lock.json") {
        Write-Host "Running npm install in frontend/..." -ForegroundColor Gray
        & npm install
    } else {
        & npm install
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed in frontend/."
        exit 1
    }
    Write-Host "Frontend dependencies installed successfully." -ForegroundColor Green
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Developer Setup Complete!                                   " -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Verify backend\.env has valid MySQL credentials." -ForegroundColor White
Write-Host "  2. Run all tests:           .\scripts\test-all.ps1" -ForegroundColor White
Write-Host "  3. Start dev servers:       .\scripts\run-dev.ps1" -ForegroundColor White
Write-Host "  4. Build desktop app:       .\scripts\build-desktop.ps1" -ForegroundColor White
Write-Host ""
exit 0
