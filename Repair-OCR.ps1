#Requires -Version 5.1
[CmdletBinding()]
param([string]$InstallDir = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run the OCR repair on Windows.' }
$python = Join-Path $InstallDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The BeastSnip virtual environment is missing. Run the full Update-BeastSnip.ps1 updater.' }

function Invoke-TesseractInstall {
    param([switch]$Force)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Windows Package Manager (winget) is missing. Install App Installer from Microsoft Store, or install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki, then rerun this updater.'
    }
    Write-Host 'Installing the local Tesseract runtime. Accept the publisher UAC prompt if Windows shows one.' -ForegroundColor Cyan
    $arguments = @('install', '--id', 'UB-Mannheim.TesseractOCR', '--exact', '--source', 'winget', '--accept-source-agreements', '--accept-package-agreements')
    if ($Force) { $arguments += '--force' }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & winget @arguments
        $script:OcrInstallExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
}

function Invoke-OfflineOCRCheck {
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 can convert native stderr into ErrorRecords.
        # Preserve Python's exit code instead of terminating before reading it.
        $ErrorActionPreference = 'Continue'
        & $python -m beastsnip.maintenance --repair-ocr
        $script:OcrRepairExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
}

Push-Location -LiteralPath $InstallDir
try {
    $found = $false
    try {
        $location = & $python -m beastsnip.maintenance --locate-ocr 2>$null
        $found = $LASTEXITCODE -eq 0
    } catch { $found = $false }
    if (-not $found) {
        Invoke-TesseractInstall
        # Recheck actual files even if winget says the package already exists.
        try {
            $location = & $python -m beastsnip.maintenance --locate-ocr 2>$null
            $found = $LASTEXITCODE -eq 0
        } catch { $found = $false }
        if (-not $found) {
            throw "Tesseract is still unavailable after installation (winget exit $script:OcrInstallExit). Complete/allow its installer, then rerun this updater. OCR repair has not passed."
        }
    }
    Invoke-OfflineOCRCheck
    if ($script:OcrRepairExit -eq 3) {
        # The executable exists but cannot start: reinstall once to repair DLLs.
        Invoke-TesseractInstall -Force
        Invoke-OfflineOCRCheck
    }
    if ($script:OcrRepairExit -ne 0) {
        throw "OCR repair failed (exit $script:OcrRepairExit). See the specific message above. The app update is retained; rerun Repair-OCR.ps1 after resolving the reported runtime, language-download or permissions problem."
    }
    Write-Host 'Offline OCR verified and configured. Your other settings and history were preserved.' -ForegroundColor Green
} finally { Pop-Location }
