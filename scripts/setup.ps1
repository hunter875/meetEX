param([switch]$Semantic)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    $nodeVersion = [version]((node --version).TrimStart('v'))
    if ($nodeVersion -lt [version]'22.12.0') { throw 'Install Node.js 22.12+ (tested 22.20.0).' }
    python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw 'Install official Python 3.11+ with FTS5 (tested 3.13.4).' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
    & '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Extension dependency installation failed.' }
    if ($Semantic) {
        & '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements-semantic.lock --extra-index-url https://download.pytorch.org/whl/cpu
        if ($LASTEXITCODE -ne 0) { throw 'Optional CPU semantic dependency installation failed.' }
    }
    & '.\.venv\Scripts\python.exe' -c "import sqlite3; from zoneinfo import ZoneInfo; db=sqlite3.connect(':memory:'); db.execute('CREATE VIRTUAL TABLE t USING fts5(text)'); ZoneInfo('America/Los_Angeles'); print('FTS5 and timezone data ready')"
    if ($LASTEXITCODE -ne 0) { throw 'SQLite FTS5 or timezone data is unavailable.' }
    Write-Host 'Setup complete. Run .\scripts\build-extension.ps1 then .\scripts\start-backend.ps1.'
} finally { Pop-Location }
