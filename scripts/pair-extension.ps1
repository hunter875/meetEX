param([Parameter(Mandatory=$true)][ValidatePattern('^[a-p]{32}$')][string]$ExtensionId)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot '.env'
if (Test-Path -LiteralPath $envPath) { $contents = [IO.File]::ReadAllText($envPath) }
else { $contents = [IO.File]::ReadAllText((Join-Path $repoRoot '.env.example')) }
if ($contents -match '(?m)^MEET_EXTENSION_ID=') { $contents = [regex]::Replace($contents, '(?m)^MEET_EXTENSION_ID=.*$', "MEET_EXTENSION_ID=$ExtensionId") }
else { $contents += "`nMEET_EXTENSION_ID=$ExtensionId`n" }
[IO.File]::WriteAllText($envPath,$contents,(New-Object Text.UTF8Encoding($false)))
Write-Host 'Extension Origin saved. Restart backend, then enter .local\pairing-token in extension Settings.'
