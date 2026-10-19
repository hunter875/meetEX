param([switch]$Semantic)
& (Join-Path $PSScriptRoot 'meet.ps1') -Command setup -Semantic:$Semantic
exit $LASTEXITCODE
