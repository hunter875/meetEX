param([string]$DataDir)
& (Join-Path $PSScriptRoot 'meet.ps1') -Command demo -DataDir $DataDir
exit $LASTEXITCODE
