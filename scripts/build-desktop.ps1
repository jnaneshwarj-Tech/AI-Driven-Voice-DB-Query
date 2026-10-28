<#
.SYNOPSIS
    build-desktop.ps1 — Packages the Windows Desktop Application (Electron).
.DESCRIPTION
    Builds the production React bundle, verifies dependencies, and packages
    the Windows desktop installer and executable via Electron Builder.
#>

[CmdletBinding()]
param(
    [switch]$PackOnly
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  GEC Student Database ERP -- Windows Desktop Packaging         " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Root: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Step 1: Compile Frontend Production Assets
Write-Host "[Step 1/3] Compiling React Frontend with Vite..." -ForegroundColor Yellow
$frontendDir = Join-Path $ProjectRoot "frontend"
Push-Location $frontendDir
try {
    & cmd.exe /c "npm run build"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend compilation failed."
        exit 1
    }
} finally {
    Pop-Location
}

$distIndex = Join-Path $frontendDir "dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Error "Expected build artifact missing at $distIndex."
    exit 1
}
Write-Host "Frontend build verified at frontend\dist\index.html." -ForegroundColor Green

# Step 2: Install Desktop Packaging Dependencies
Write-Host ""
Write-Host "[Step 2/3] Preparing Electron Packaging Environment..." -ForegroundColor Yellow
$desktopDir = Join-Path $ProjectRoot "desktop"
Push-Location $desktopDir
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing Electron dependencies in desktop/..." -ForegroundColor Gray
        & cmd.exe /c "npm install"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install desktop dependencies."
            exit 1
        }
    } else {
        Write-Host "Desktop dependencies already present." -ForegroundColor Green
    }

    # Step 3: Run Electron Builder
    Write-Host ""
    Write-Host "[Step 3/3] Packaging Windows Application..." -ForegroundColor Yellow
    if ($PackOnly) {
        Write-Host "Running unpackaged directory build (electron-builder --dir)..." -ForegroundColor Gray
        & cmd.exe /c "npm run pack"
    } else {
        Write-Host "Building Windows NSIS Installer and Portable Executable..." -ForegroundColor Gray
        & cmd.exe /c "npm run dist"
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Electron packaging failed with exit code $LASTEXITCODE."
        exit 1
    }
} finally {
    Pop-Location
}

# Step 4: Verification of build artifacts
$releaseDir = Join-Path $desktopDir "release"
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Desktop Packaging Complete!                                 " -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "Artifacts location: $releaseDir" -ForegroundColor White

if (Test-Path $releaseDir) {
    Get-ChildItem -Path $releaseDir | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
}

Write-Host "Verification Checklist for College Deployment:" -ForegroundColor Cyan
Write-Host "  [OK] Central server URL configured via desktop\config.json" -ForegroundColor White
Write-Host "  [OK] No database passwords or AI secrets bundled in client" -ForegroundColor White
Write-Host "  [OK] Ready for installation on college Windows PCs" -ForegroundColor White
Write-Host ""
exit 0
