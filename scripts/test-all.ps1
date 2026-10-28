<#
.SYNOPSIS
    test-all.ps1 — Runs all automated test suites, build checks, and validation.
.DESCRIPTION
    Executes backend unittest battery, frontend build validation, and security tests.
#>

[CmdletBinding()]
param(
    [string]$Database = "student_db_staging",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Continue"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  GEC Student Database ERP -- Master Automated Test Battery    " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Database Target: $Database" -ForegroundColor Gray
Write-Host ""

$OverallPassed = $true

# 1. Environment & Configuration Template Verification
Write-Host "[1/3] Validating Configuration Templates..." -ForegroundColor Yellow
$checkScript = Join-Path $ScriptRoot "check-environment.ps1"
if (Test-Path $checkScript) {
    & $checkScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host " [FAIL] Environment check failed." -ForegroundColor Red
        $OverallPassed = $false
    } else {
        Write-Host " [PASS] Configuration templates verified." -ForegroundColor Green
    }
}

# 2. Frontend Build Verification
if (-not $SkipFrontend) {
    Write-Host ""
    Write-Host "[2/3] Validating Frontend Production Build (Vite)..." -ForegroundColor Yellow
    $frontendDir = Join-Path $ProjectRoot "frontend"
    Push-Location $frontendDir
    try {
        & npm run build
        if ($LASTEXITCODE -eq 0 -and (Test-Path "dist\index.html")) {
            Write-Host " [PASS] Frontend compiled cleanly into dist/." -ForegroundColor Green
        } else {
            Write-Host " [FAIL] Frontend build failed." -ForegroundColor Red
            $OverallPassed = $false
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "[2/3] Skipping Frontend Build Check (-SkipFrontend specified)." -ForegroundColor Gray
}

# 3. Backend Unit and Security Test Suite
Write-Host ""
Write-Host "[3/3] Executing Backend Unit and Security Test Battery..." -ForegroundColor Yellow
$venvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host " [FAIL] Python virtual environment missing at backend\.venv." -ForegroundColor Red
    $OverallPassed = $false
} else {
    # Set staging test database explicitly
    $oldDb = $env:MYSQL_DB
    $cleanDb = $Database.Trim()
    $env:MYSQL_DB = $cleanDb
    try {
        & $venvPython -m unittest discover -s (Join-Path $ProjectRoot "backend\tests") -p "test_*.py"
        if ($LASTEXITCODE -eq 0) {
            Write-Host " [PASS] All backend unit tests passed." -ForegroundColor Green
        } else {
            Write-Host " [FAIL] Some backend tests failed with exit code $LASTEXITCODE." -ForegroundColor Red
            $OverallPassed = $false
        }
    } finally {
        $env:MYSQL_DB = $oldDb
    }
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
if ($OverallPassed) {
    Write-Host "  TEST RESULT: ALL TEST SUITES PASSED (PASS)                   " -ForegroundColor Green
    Write-Host "==============================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "  TEST RESULT: FAILURES DETECTED (FAIL)                       " -ForegroundColor Red
    Write-Host "==============================================================" -ForegroundColor Cyan
    exit 1
}
