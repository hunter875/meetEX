param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('setup','build','start','stop','doctor','test','backup','restore','rotate-token','update','package')]
    [string]$Command,
    [string]$DataDir,
    [string]$Path,
    [switch]$Semantic,
    [switch]$Browser
)
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'meet.py'
$arguments = @($entry, $Command)
if ($DataDir) { $arguments += @('--data-dir', $DataDir) }
if ($Path) { $arguments += @('--path', $Path) }
if ($Semantic) { $arguments += '--semantic' }
if ($Browser) { $arguments += '--browser' }
& python @arguments
exit $LASTEXITCODE
