# Task 0.3 helper: verify PostgreSQL 15 + PostGIS and create the two databases.
# Usage:  .\scripts\check-postgis.ps1 -PgUser postgres
param([string]$PgUser = "postgres", [string]$PgHost = "localhost", [int]$PgPort = 5432)

$psql = "psql"
& $psql -h $PgHost -p $PgPort -U $PgUser -c "SELECT version();"
foreach ($db in @("geoguard_db", "geoguard_test")) {
  & $psql -h $PgHost -p $PgPort -U $PgUser -tc "SELECT 1 FROM pg_database WHERE datname='$db'" | Select-String 1 | Out-Null
  if (-not $?) { & $psql -h $PgHost -p $PgPort -U $PgUser -c "CREATE DATABASE $db;" }
  & $psql -h $PgHost -p $PgPort -U $PgUser -d $db -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pgcrypto;"
  & $psql -h $PgHost -p $PgPort -U $PgUser -d $db -c "SELECT PostGIS_Full_Version();"
}
