# PowerShell setup script for Windows
# Sets up the environment variable with the full path to the database.

$env:CADBPATH = "$(Get-Location)\curling_data.db"
Write-Host "CADBPATH environment variable set to: $env:CADBPATH"

# Verify the database exists
if (Test-Path "curling_data.db") {
    Write-Host "✅ Database file exists at: $(Get-Location)\curling_data.db"
} else {
    Write-Host "❌ Database file not found. Run 'python create_database.py' to create it."
}