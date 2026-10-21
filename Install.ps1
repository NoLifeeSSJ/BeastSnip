#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallDir = 'C:\SnipV1',
    [switch]$InstallOCR,
    [switch]$CloseRunningApp,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'BeastSnip installation requires Windows 11.' }
$expectedVersion = '2.0.0'

function Find-BeastPython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($command in @('py', 'python', 'python3')) {
        if (Get-Command $command -ErrorAction SilentlyContinue) {
            try {
                $arguments = if ($command -eq 'py') { @('-3.12', '-c', 'import sys; print(sys.executable)') } else { @('-c', 'import sys; print(sys.executable)') }
                $result = & $command @arguments 2>$null
                if ($LASTEXITCODE -eq 0 -and $result) { $candidates.Add([string]($result | Select-Object -Last 1)) }
            } catch { }
        }
    }
    foreach ($path in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", 'C:\Python312\python.exe')) {
        if (Test-Path -LiteralPath $path) { $candidates.Add($path) }
    }
    foreach ($candidate in $candidates) {
        try {
            & $candidate -c "import sys,struct; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) and struct.calcsize('P')==8 else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    return $null
}

$python = Find-BeastPython
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/ (include the Python launcher), then rerun this command. Alternatively install App Installer from Microsoft Store to enable winget.'
    }
    Write-Host 'Installing Python 3.12 for your Windows account...'
    & winget install --id Python.Python.3.12 --exact --scope user --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed (exit $LASTEXITCODE). Install Python 3.12 manually and rerun setup." }
    $python = Find-BeastPython
    if (-not $python) { throw 'Python was installed but not found. Open a new PowerShell window and run setup again.' }
}

$source = $PSScriptRoot
try { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null } catch {
    throw "Cannot create $InstallDir. Choose a folder you own with -InstallDir, for example `$env:LOCALAPPDATA\BeastSnipApp. $($_.Exception.Message)"
}
$destination = (Resolve-Path -LiteralPath $InstallDir).Path
Write-Host '[1/7] Checking the running app...' -ForegroundColor Cyan
. (Join-Path $PSScriptRoot 'tools\Update-Helpers.ps1')
Close-BeastSnipForUpdate -InstallDir $destination -CloseRunningApp:$CloseRunningApp
Write-Host '[2/7] Backing up and updating application files...' -ForegroundColor Cyan
if (-not [string]::Equals($source.TrimEnd('\'), $destination.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) {
    # Source-only allowlist: never copy an existing venv, user history, or Git data.
    $files = @('beastsnip', 'tests', 'tools', 'run_beastsnip.py', 'requirements.txt', 'requirements-build.txt', 'Install.ps1', 'Update.ps1', 'Repair-OCR.ps1', 'Launch.ps1', 'Launch.cmd', 'Build.ps1', 'README.md', 'VERIFICATION.md', 'CHANGELOG.md')
    $backupRoot = Join-Path $env:LOCALAPPDATA ('BeastSnip\setup-backups\' + [guid]::NewGuid().ToString('N'))
    foreach ($file in $files) {
        $from = Join-Path $source $file
        $to = Join-Path $destination $file
        if (-not (Test-Path -LiteralPath $from)) { throw "Installer payload is missing $file." }
        if (Test-Path -LiteralPath $to) {
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Copy-Item -LiteralPath $to -Destination (Join-Path $backupRoot $file) -Recurse -Force
        }
        Copy-Item -LiteralPath $from -Destination $destination -Recurse -Force
    }
    if (Test-Path -LiteralPath $backupRoot) { Write-Host "Previous application files backed up to $backupRoot" }
}
Clear-BeastSnipBytecode -InstallDir $destination

Push-Location -LiteralPath $destination
try {
    Write-Host '[3/7] Checking Python and installing dependencies...' -ForegroundColor Cyan
    $venv = Join-Path $destination '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venv)) {
        & $python -m venv (Join-Path $destination '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    }
    & $venv -m pip install --disable-pip-version-check -r (Join-Path $destination 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network connection and the pip error above, then rerun setup.' }
    & $venv -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Installed dependencies are inconsistent.' }
    & $venv -c "from beastsnip.app import MainWindow; from beastsnip.windows import grab_pixels; print('BeastSnip imports OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Application import verification failed.' }
    $installedVersion = & $venv -c "import beastsnip; print(beastsnip.__version__)"
    if ($LASTEXITCODE -ne 0 -or ([string]$installedVersion).Trim() -ne $expectedVersion) {
        throw "Application version verification failed. Expected $expectedVersion, got $installedVersion. The update has not completed."
    }
    Write-Host '[4/7] Running application startup and editing tests...' -ForegroundColor Cyan
    $previousDataDir = $env:BEASTSNIP_DATA_DIR
    $smokeDir = Join-Path ([System.IO.Path]::GetTempPath()) ('BeastSnip-check-' + [guid]::NewGuid().ToString('N'))
    try {
        $env:BEASTSNIP_DATA_DIR = $smokeDir
        & $venv -m beastsnip --smoke-test
        if ($LASTEXITCODE -ne 0) { throw 'Application startup verification failed. See the error above.' }
        & $venv -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Application self-tests failed. See the error above.' }
        & (Join-Path $destination 'tests\test_updater.ps1')
    } finally {
        if ($null -eq $previousDataDir) { Remove-Item Env:BEASTSNIP_DATA_DIR -ErrorAction SilentlyContinue } else { $env:BEASTSNIP_DATA_DIR = $previousDataDir }
        if (Test-Path -LiteralPath $smokeDir) { Remove-Item -LiteralPath $smokeDir -Recurse -Force }
    }

    if ($InstallOCR) {
        Write-Host '[5/7] Installing, configuring and testing local OCR...' -ForegroundColor Cyan
        & (Join-Path $destination 'Repair-OCR.ps1') -InstallDir $destination
    } else {
        Write-Host '[5/7] OCR installation was not requested.'
    }

    Write-Host '[6/7] Testing Windows monitor mapping and capture buffers...' -ForegroundColor Cyan
    & $venv -m beastsnip.maintenance --check-native
    if ($LASTEXITCODE -ne 0) { throw 'Native monitor/capture validation failed. See the display diagnosis above; the updater has not passed all checks.' }

    Write-Host 'Preparing automatic PNG saving in C:\SnipsV1\Screenshots...' -ForegroundColor Cyan
    & $venv -m beastsnip.maintenance --configure-autosave 'C:\SnipsV1\Screenshots'
    if ($LASTEXITCODE -ne 0) { throw 'The Screenshots folder or auto-save configuration could not be prepared. See the folder error above.' }

    Write-Host '[7/7] Updating the desktop shortcut...' -ForegroundColor Cyan
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    if (-not $desktop) { throw 'Windows did not return a desktop folder for this user.' }
    $shell = New-Object -ComObject WScript.Shell
    $shortcutPath = Join-Path $desktop 'BeastSnip.lnk'
    if (Test-Path -LiteralPath $shortcutPath) {
        $prior = $shell.CreateShortcut($shortcutPath)
        if ($prior.TargetPath -ne (Join-Path $destination '.venv\Scripts\pythonw.exe')) {
            $priorBackup = Join-Path $desktop ('BeastSnip-previous-' + [guid]::NewGuid().ToString('N') + '.lnk')
            Copy-Item -LiteralPath $shortcutPath -Destination $priorBackup
        }
    }
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $destination '.venv\Scripts\pythonw.exe'
    $shortcut.Arguments = '"' + (Join-Path $destination 'run_beastsnip.py') + '"'
    $shortcut.WorkingDirectory = $destination
    $shortcut.IconLocation = (Join-Path $destination 'beastsnip\resources\beastsnip.ico') + ',0'
    $shortcut.Description = 'BeastSnip - private screenshots and annotations'
    $shortcut.Save()
    Write-Host "`nUPDATE COMPLETE - BeastSnip $expectedVersion verified in $destination" -ForegroundColor Green
    Write-Host "Desktop shortcut: $shortcutPath"
    Write-Host "Launch: & '$destination\Launch.ps1'"
    if ($Launch) { & (Join-Path $destination 'Launch.ps1') }
} finally { Pop-Location }
