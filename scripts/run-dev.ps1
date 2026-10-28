<#
.SYNOPSIS
    run-dev.ps1 — Launches backend and frontend development services concurrently.
.DESCRIPTION
    Starts the FastAPI backend at http://localhost:8000 and the Vite frontend at http://localhost:5173.
#>

[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Starting GEC Student Database ERP — Development Servers      " -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

$venvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment missing. Please run .\scripts\setup-dev.ps1 first."
    exit 1
}

$backendEnv = Join-Path $ProjectRoot "backend\.env"
if (-not (Test-Path $backendEnv)) {
    Write-Error "Configuration missing at backend\.env. Please copy backend\.env.example and configure credentials."
    exit 1
}

Write-Host "Starting Backend (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Yellow
$backendJob = Start-Process -FilePath $venvPython -ArgumentList "main.py" -WorkingDirectory (Join-Path $ProjectRoot "backend") -PassThru

Write-Host "Starting Frontend (Vite on http://localhost:5173)..." -ForegroundColor Yellow
$frontendJob = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory (Join-Path $ProjectRoot "frontend") -PassThru

Start-Sleep -Seconds 3

if (-not $NoBrowser) {
    Write-Host "Opening application in browser: http://localhost:5173" -ForegroundColor Green
    Start-Process "http://localhost:5173"
}

Write-Host ""
Write-Host "Services running in background:" -ForegroundColor Cyan
Write-Host "  - Backend PID:  $($backendJob.Id) (http://localhost:8000)" -ForegroundColor White
Write-Host "  - Frontend PID: $($frontendJob.Id) (http://localhost:5173)" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C or Enter to stop both development servers..." -ForegroundColor Yellow

try {
    [Console]::ReadLine() | Out-Null
} finally {
    Write-Host "Stopping development servers..." -ForegroundColor Gray
    if ($backendJob -and -not $backendJob.HasExited) {
        Stop-Process -Id $backendJob.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendJob -and -not $frontendJob.HasExited) {
        Stop-Process -Id $frontendJob.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Services stopped cleanly." -ForegroundColor Green
}
