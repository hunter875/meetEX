$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    & '.\.venv\Scripts\python.exe' scripts\load_demo.py
    if ($LASTEXITCODE -ne 0) { throw 'Start backend first, then retry loading demo data.' }
} finally { Pop-Location }
