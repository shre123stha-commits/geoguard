# Migrate geoguard_db to the latest schema and create the first admin (Windows, native PostgreSQL).
# Run from the repo root with the backend venv activated:  .\scripts\db-migrate.ps1
# Requires backend\.env with DATABASE_URL, FIRST_ADMIN_EMAIL, FIRST_ADMIN_PASSWORD.
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot\..\backend"
try {
  alembic upgrade head
  python scripts\seed.py --sample-parcels ..\data\samples\parcels.geojson
  Write-Host "`nDone. Run 'alembic current' to see the schema version." -ForegroundColor Green
} finally { Pop-Location }
