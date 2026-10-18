param([switch]$Browser)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    & '.\.venv\Scripts\python.exe' -m pytest -q --junitxml=docs\evidence\backend-tests.xml
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Extension tests failed.' }
    npm.cmd run contracts
    if ($LASTEXITCODE -ne 0) { throw 'OpenAPI contract check failed.' }
    & '.\.venv\Scripts\python.exe' scripts\benchmark.py
    if ($LASTEXITCODE -ne 0) { throw 'Retrieval benchmark failed.' }
    if ($Browser) {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
        npx.cmd playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed.' }
        npm.cmd run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Extension browser tests failed.' }
    }
} finally { Pop-Location }
