param([string]$DataDir)
& (Join-Path $PSScriptRoot 'meet.ps1') -Command start -DataDir $DataDir
exit $LASTEXITCODE
