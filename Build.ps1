#Requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows executable on Windows; PyInstaller does not cross-compile.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    . (Join-Path $PSScriptRoot 'tools/Install-Transaction.ps1')
    $python = Get-BeastSnipPython -InstallDir $PSScriptRoot
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run Install.ps1 first.' }
    & $python -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir --name BeastSnip --icon beastsnip/resources/beastsnip.ico --add-data 'beastsnip/resources;beastsnip/resources' --collect-data PySide6 run_beastsnip.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $envBefore = $env:BEASTSNIP_DATA_DIR
    $checkDir = Join-Path ([IO.Path]::GetTempPath()) ('BeastSnip-build-check-' + [guid]::NewGuid().ToString('N'))
    try {
        $env:BEASTSNIP_DATA_DIR = $checkDir
        $check = Start-Process -FilePath (Join-Path $PSScriptRoot 'dist\BeastSnip\BeastSnip.exe') -ArgumentList '--smoke-test' -Wait -PassThru
        if ($check.ExitCode -ne 0) { throw "Packaged startup check failed (exit $($check.ExitCode))." }
    } finally {
        if ($null -eq $envBefore) { Remove-Item Env:BEASTSNIP_DATA_DIR -ErrorAction SilentlyContinue } else { $env:BEASTSNIP_DATA_DIR = $envBefore }
        if (Test-Path -LiteralPath $checkDir) { Remove-Item -LiteralPath $checkDir -Recurse -Force }
    }
    Write-Host 'Build complete: dist\BeastSnip\BeastSnip.exe. Distribute the entire BeastSnip folder, including _internal. Tesseract remains an optional separate installation.' -ForegroundColor Green
} finally { Pop-Location }
