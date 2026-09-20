# Back up the database (pg_dump, custom format) and the data folder (evidence, reports, samples,
# eval labels) into backups\<timestamp>\. Works with Supabase or local PostgreSQL.
# Usage (repo root, backend venv active):  .\scripts\backup.ps1   [-OutDir D:\geoguard-backups]
# Needs pg_dump on PATH (ships with PostgreSQL; on Windows also in the Supabase CLI or EDB tools).
param([string]$OutDir = "$PSScriptRoot\..\backups")
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
$env = Get-Content "$root\backend\.env" | Where-Object { $_ -match '^DATABASE_URL=' }
if (-not $env) { throw "DATABASE_URL not found in backend\.env" }
$url = ($env -split '=', 2)[1].Trim()
# pg_dump wants a plain postgresql:// URL
$url = $url -replace '^postgresql\+psycopg://', 'postgresql://'
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $OutDir $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "Dumping database ..." 
pg_dump --format=custom --no-owner --no-privileges --file "$dest\db.dump" "$url"

Write-Host "Copying data folder (without cache) ..."
$data = Join-Path $root "data"
robocopy $data "$dest\data" /E /XD cache local_scenes composites previews /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

Copy-Item "$root\backend\.env.example" "$dest\env.example.txt"
Write-Host "Backup complete: $dest" -ForegroundColor Green
Write-Host "Keep backend\.env somewhere safe separately (it holds secrets and is NOT copied)."
