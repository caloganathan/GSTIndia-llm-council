# LLM Council - Windows launcher
# Opens the backend and frontend, each in its own PowerShell window.
# Usage:  right-click > "Run with PowerShell", or from a terminal:  .\start.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Test-Path (Join-Path $root ".env"))) {
    Write-Host "WARNING: no .env found in $root - the backend will 401 without OPENROUTER_API_KEY." -ForegroundColor Yellow
}

Write-Host "Starting LLM Council..." -ForegroundColor Cyan

# Backend (FastAPI on :8001)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; Write-Host 'Backend - LLM Council' -ForegroundColor Green; uv run python -m backend.main"
)

# Frontend (Vite dev server on :5173)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\frontend'; Write-Host 'Frontend - LLM Council' -ForegroundColor Green; npm run dev"
)

Write-Host ""
Write-Host "LLM Council is launching in two new windows:" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8001"
Write-Host "  Frontend: http://localhost:5173"
Write-Host ""
Write-Host "Open http://localhost:5173 in your browser once both windows are ready."
Write-Host "Close the two windows (or Ctrl+C in each) to stop."
