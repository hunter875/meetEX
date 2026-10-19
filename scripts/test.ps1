param([switch]$Browser)
& (Join-Path $PSScriptRoot 'meet.ps1') -Command test -Browser:$Browser
exit $LASTEXITCODE
