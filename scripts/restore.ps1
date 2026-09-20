# Restore a backup made by backup.ps1 into the database named in backend\.env and the data folder.
# Usage (repo root, backend venv active):  .\scripts\restore.ps1 -From .\backups\20260920-120000
# The target database must exist and be EMPTY (or pass -Clean to drop existing objects first).
param(
  [Parameter(Mandatory = $true)][string]$From,
  [switch]$Clean
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
$env = Get-Content "$root\backend\.env" | Where-Object { $_ -match '^DATABASE_URL=' }
$url = (($env -split '=', 2)[1].Trim()) -replace '^postgresql\+psycopg://', 'postgresql://'
if (-not (Test-Path "$From\db.dump")) { throw "No db.dump in $From" }

$args = @("--no-owner", "--no-privileges", "--dbname", $url)
if ($Clean) { $args += @("--clean", "--if-exists") }
Write-Host "Restoring database ..."
pg_restore @args "$From\db.dump"

Write-Host "Restoring data folder ..."
robocopy "$From\data" (Join-Path $root "data") /E /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

Push-Location "$root\backend"
try { alembic current } finally { Pop-Location }
Write-Host "Restore complete. Start the backend and open /health to confirm." -ForegroundColor Green
