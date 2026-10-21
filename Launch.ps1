#Requires -Version 5.1
[CmdletBinding()]
param([switch]$Console)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot ('.venv\Scripts\' + $(if ($Console) { 'python.exe' } else { 'pythonw.exe' }))
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Install.ps1 first to prepare BeastSnip.' }
$entry = Join-Path $PSScriptRoot 'run_beastsnip.py'
if ($Console) {
    Push-Location -LiteralPath $PSScriptRoot
    try { & $python $entry; if ($LASTEXITCODE -ne 0) { throw "BeastSnip exited with code $LASTEXITCODE" } } finally { Pop-Location }
} else {
    Start-Process -FilePath $python -ArgumentList ('"' + $entry + '"') -WorkingDirectory $PSScriptRoot
}
