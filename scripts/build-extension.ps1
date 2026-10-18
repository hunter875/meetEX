$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Extension build failed.' }
    Write-Host 'Chrome -> chrome://extensions -> Developer mode -> Load unpacked -> D:\meetEX\extension\dist'
} finally { Pop-Location }
