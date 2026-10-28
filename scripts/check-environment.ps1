<#
.SYNOPSIS
    check-environment.ps1 — Audits developer and college host prerequisites.
#>

[CmdletBinding()]
param(
    [switch]$CollegeServerMode
)

$ErrorActionPreference = "Continue"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  GEC Student Database ERP -- Environment Verification Audit   " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Target Root: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

$AllPassed = $true

# 1. Python Version Check (>= 3.10 required)
Write-Host "[1/6] Checking Python installation..." -NoNewline
try {
    $pyVerRaw = & python --version 2>&1
    $pyVer = "$pyVerRaw".Trim()
    if ($LASTEXITCODE -eq 0 -and $pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 10) {
            Write-Host " [PASS] $pyVer" -ForegroundColor Green
        } else {
            Write-Host " [FAIL] $pyVer detected; Python 3.10+ required" -ForegroundColor Red
            $AllPassed = $false
        }
    } else {
        Write-Host " [FAIL] Python not found in PATH" -ForegroundColor Red
        $AllPassed = $false
    }
} catch {
    Write-Host " [FAIL] Python check error: $_" -ForegroundColor Red
    $AllPassed = $false
}

# 2. Node.js & npm Check
Write-Host "[2/6] Checking Node.js and npm..." -NoNewline
try {
    $nodeVerRaw = & node --version 2>&1
    $npmVerRaw = & npm --version 2>&1
    $nodeVer = "$nodeVerRaw".Trim()
    $npmVer = "$npmVerRaw".Trim()
    if ($LASTEXITCODE -eq 0 -and $nodeVer -match "v(\d+)\.") {
        $nodeMajor = [int]$Matches[1]
        if ($nodeMajor -ge 18) {
            Write-Host " [PASS] Node $nodeVer, npm $npmVer" -ForegroundColor Green
        } else {
            Write-Host " [WARN] Node $nodeVer detected; Node 18+ recommended" -ForegroundColor Yellow
        }
    } else {
        if ($CollegeServerMode) {
            Write-Host " [SKIP] Node.js not strictly required on backend-only server" -ForegroundColor Yellow
        } else {
            Write-Host " [FAIL] Node.js not found in PATH; required for frontend and desktop packaging" -ForegroundColor Red
            $AllPassed = $false
        }
    }
} catch {
    Write-Host " [FAIL] Node.js check error: $_" -ForegroundColor Red
    $AllPassed = $false
}

# 3. Python Virtual Environment Check
Write-Host "[3/6] Checking Python Virtual Environment..." -NoNewline
$venvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host " [PASS] Found at backend\.venv" -ForegroundColor Green
} else {
    Write-Host " [WARN] Missing at backend\.venv; run scripts\setup-dev.ps1" -ForegroundColor Yellow
}

# 4. Configuration Template vs Live Environment Files
Write-Host "[4/6] Checking Configuration Files..." -NoNewline
$backendEnv = Join-Path $ProjectRoot "backend\.env"
$backendEnvEx = Join-Path $ProjectRoot "backend\.env.example"

if (Test-Path $backendEnv) {
    Write-Host " [PASS] backend\.env exists" -ForegroundColor Green
} else {
    if (Test-Path $backendEnvEx) {
        Write-Host " [WARN] backend\.env missing; copy from backend\.env.example" -ForegroundColor Yellow
    } else {
        Write-Host " [FAIL] Both backend\.env and backend\.env.example are missing" -ForegroundColor Red
        $AllPassed = $false
    }
}

# 5. Required Project Assets & Directories
Write-Host "[5/6] Checking Directory Structure and Core Files..." -NoNewline
$criticalPaths = @(
    "backend\main.py",
    "backend\requirements.txt",
    "frontend\package.json",
    "frontend\src\main.jsx",
    "database\schema.sql"
)
$missingFiles = @()
foreach ($rel in $criticalPaths) {
    $full = Join-Path $ProjectRoot $rel
    if (-not (Test-Path $full)) {
        $missingFiles += $rel
    }
}
if ($missingFiles.Count -eq 0) {
    Write-Host " [PASS] All core files present" -ForegroundColor Green
} else {
    $missingJoined = $missingFiles -join ", "
    Write-Host " [FAIL] Missing files: $missingJoined" -ForegroundColor Red
    $AllPassed = $false
}

# 6. Storage & Upload Directories
Write-Host "[6/6] Checking Storage and Backup Directories..." -NoNewline
$storageDirs = @("backend\uploads", "backend\backups")
foreach ($dir in $storageDirs) {
    $fullDir = Join-Path $ProjectRoot $dir
    if (-not (Test-Path $fullDir)) {
        New-Item -ItemType Directory -Path $fullDir -Force | Out-Null
    }
    $keepFile = Join-Path $fullDir ".gitkeep"
    if (-not (Test-Path $keepFile)) {
        Set-Content -Path $keepFile -Value ""
    }
}
Write-Host " [PASS] backend\uploads and backend\backups verified" -ForegroundColor Green

Write-Host ""
if ($AllPassed) {
    Write-Host ">>> ENVIRONMENT AUDIT SUCCESSFUL: System is ready for development or build." -ForegroundColor Green
    exit 0
} else {
    Write-Host ">>> ENVIRONMENT AUDIT FAILED: Please resolve the issues flagged with [FAIL] above." -ForegroundColor Red
    exit 1
}
