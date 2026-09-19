# Starts the FastAPI backend and the Vite frontend in two PowerShell windows.
# Usage (from repo root):  .\scripts\start-dev.ps1
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$root\backend'; & '$root\.venv\Scripts\Activate.ps1'; uvicorn app.main:app --reload --port 8000"
)
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$root\frontend'; npm run dev"
)
Write-Host "Backend: http://localhost:8000/docs   Frontend: http://localhost:5173"
