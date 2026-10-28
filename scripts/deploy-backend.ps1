<#
.SYNOPSIS
    deploy-backend.ps1 — College IT Administrator Backend Deployment Script.
.DESCRIPTION
    Validates host environment, verifies MySQL connectivity, ensures required directories,
    verifies configuration without exposing secrets, and provisions the FastAPI service.
#>

[CmdletBinding()]
param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$StartService
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  GEC College Server -- Backend Production Deployment Engine   " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ("Target Host: {0} on port {1}" -f $BindHost, $Port) -ForegroundColor Gray
Write-Host ""

# Step 1: Pre-flight audit in Server Mode
Write-Host "[Step 1/5] Auditing server environment prerequisites..." -ForegroundColor Yellow
$checkScript = Join-Path $ScriptRoot "check-environment.ps1"
if (Test-Path $checkScript) {
    & $checkScript -CollegeServerMode
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Server environment check failed. Please resolve prerequisites."
        exit 1
    }
}

# Step 2: Virtual environment validation
Write-Host ""
Write-Host "[Step 2/5] Checking Python virtual environment..." -ForegroundColor Yellow
$venvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python virtual environment at backend\.venv..." -ForegroundColor Gray
    & python -m venv (Join-Path $ProjectRoot "backend\.venv")
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")
} else {
    Write-Host "Virtual environment verified." -ForegroundColor Green
}

# Step 3: Production Configuration Audit
Write-Host ""
Write-Host "[Step 3/5] Validating production backend\.env configuration..." -ForegroundColor Yellow
$backendEnv = Join-Path $ProjectRoot "backend\.env"
if (-not (Test-Path $backendEnv)) {
    Write-Error "CRITICAL: backend\.env not found! Please copy backend\.env.example to backend\.env and configure production MySQL credentials and SECRET_KEY."
    exit 1
}

# Run safe startup validation
& $venvPython -c "import sys; sys.path.insert(0, 'backend'); from config import settings; settings.validate_startup(); print('[OK] Configuration validated successfully.')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Configuration validation failed. Check backend\.env variables."
    exit 1
}

# Step 4: Storage directories and permissions
Write-Host ""
Write-Host "[Step 4/5] Verifying persistent storage and backup paths..." -ForegroundColor Yellow
$dirs = @("backend\uploads", "backend\backups")
foreach ($d in $dirs) {
    $full = Join-Path $ProjectRoot $d
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Path $full -Force | Out-Null
    }
}
Write-Host "Storage directories verified." -ForegroundColor Green

# Step 5: Service Execution or Service Registration Instructions
Write-Host ""
Write-Host "[Step 5/5] Production Service Launch..." -ForegroundColor Yellow

if ($StartService) {
    Write-Host ("Starting FastAPI Uvicorn ASGI Server on {0}:{1}..." -f $BindHost, $Port) -ForegroundColor Green
    Set-Location (Join-Path $ProjectRoot "backend")
    & $venvPython -m uvicorn main:app --host $BindHost --port $Port --workers 4
} else {
    Write-Host "Backend environment is fully prepared." -ForegroundColor Green
    Write-Host ""
    Write-Host "To start the production server interactively, run:" -ForegroundColor Cyan
    Write-Host "  cd backend" -ForegroundColor White
    Write-Host "  .venv\Scripts\activate" -ForegroundColor White
    Write-Host ("  uvicorn main:app --host {0} --port {1} --workers 4" -f $BindHost, $Port) -ForegroundColor White
    Write-Host ""
    Write-Host "To run as a permanent Windows Service (NSSM recommended):" -ForegroundColor Cyan
    Write-Host "  nssm install GECStudentDBService `"$venvPython`" `"main.py`"" -ForegroundColor White
    Write-Host "  nssm set GECStudentDBService AppDirectory `"$($ProjectRoot)\backend`"" -ForegroundColor White
    Write-Host "  nssm start GECStudentDBService" -ForegroundColor White
    Write-Host ""
}

Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Backend Production Deployment Verification Succeeded!       " -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
exit 0
