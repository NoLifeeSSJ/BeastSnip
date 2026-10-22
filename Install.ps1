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
$expectedVersion = '2.1.0'

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
. (Join-Path $source 'tools\Update-Helpers.ps1')
. (Join-Path $source 'tools\Install-Transaction.ps1')
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$destination = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $InstallDir).Path)
$lockPath = Join-Path $destination '.beastsnip-update.lock'
try { $updateLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) } catch {
    throw 'Another BeastSnip update is running or this folder is not writable. Wait for it to finish, then retry.'
}
$runtimeId = [guid]::NewGuid().ToString('N')
$runtimeDir = Join-Path (Join-Path $destination '.beastsnip-runtimes') $runtimeId
$candidate = Join-Path $destination ('.beastsnip-stage-' + [guid]::NewGuid().ToString('N'))
$transaction = $null
$committed = $false
$closedPrevious = $false
$previousExists = Test-Path -LiteralPath (Join-Path $destination 'run_beastsnip.py')
$files = @('beastsnip','tests','tools','run_beastsnip.py','requirements.txt','requirements-build.txt','Install.ps1','Update.ps1','Repair-OCR.ps1','Launch.ps1','Launch.cmd','Build.ps1','README.md','VERIFICATION.md','CHANGELOG.md')
try {
    Write-BeastSnipUpdateStatus 'staging' '[1/8] Preparing a separate candidate. The current application and Python runtime are retained.' $expectedVersion
    Repair-BeastSnipInterruptedActivation -InstallDir $destination
    New-Item -ItemType Directory -Path $candidate -Force | Out-Null
    foreach ($file in $files) {
        $from = Join-Path $source $file
        if (-not (Test-Path -LiteralPath $from)) { throw "The installer payload is missing $file." }
        Copy-Item -LiteralPath $from -Destination $candidate -Recurse -Force
    }
    Clear-BeastSnipBytecode -InstallDir $candidate
    Write-BeastSnipJson -Path (Join-Path $candidate 'runtime.json') -Value @{schema=1; runtime=$runtimeId; version=$expectedVersion}
    Write-BeastSnipUpdateStatus 'staging' '[2/8] Preparing the new Python runtime and dependencies...' $expectedVersion
    & $python -m venv $runtimeDir
    if ($LASTEXITCODE -ne 0) { throw 'The candidate Python runtime could not be created.' }
    $candidatePython = Join-Path $runtimeDir 'Scripts/python.exe'
    & $candidatePython -m pip install --disable-pip-version-check -r (Join-Path $candidate 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Candidate dependency installation failed. The previous application has not been replaced.' }
    & $candidatePython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'The candidate dependencies are inconsistent.' }
    Push-Location -LiteralPath $candidate
    try {
        Write-BeastSnipUpdateStatus 'checking' '[3/8] Testing candidate startup, editing, recovery, library and scrolling algorithms...' $expectedVersion
        $previousDataDir = $env:BEASTSNIP_DATA_DIR
        $smokeDir = Join-Path ([IO.Path]::GetTempPath()) ('BeastSnip-check-' + [guid]::NewGuid().ToString('N'))
        try {
            $env:BEASTSNIP_DATA_DIR = $smokeDir
            & $candidatePython -m beastsnip --smoke-test
            if ($LASTEXITCODE -ne 0) { throw 'Candidate startup failed. No live application files were replaced.' }
            & $candidatePython -m unittest discover -s tests -v
            if ($LASTEXITCODE -ne 0) { throw 'Candidate self-tests failed. No live application files were replaced.' }
            & (Join-Path $candidate 'tests/test_updater.ps1')
            & (Join-Path $candidate 'tests/test_transactions.ps1')
        } finally {
            if ($null -eq $previousDataDir) { Remove-Item Env:BEASTSNIP_DATA_DIR -ErrorAction SilentlyContinue } else { $env:BEASTSNIP_DATA_DIR = $previousDataDir }
            Remove-Item -LiteralPath $smokeDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-BeastSnipUpdateStatus 'checking' '[4/8] Closing BeastSnip and recording rollback data...' $expectedVersion
        Close-BeastSnipForUpdate -InstallDir $destination -CloseRunningApp:$CloseRunningApp
        $closedPrevious = $previousExists
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        if (-not $desktop) { throw 'Windows did not return a desktop folder.' }
        $shortcutPath = Join-Path $desktop 'BeastSnip.lnk'
        $transaction = New-BeastSnipTransaction -InstallDir $destination -Names ($files + @('runtime.json')) -Runtime $runtimeId -ShortcutPath $shortcutPath
        Write-BeastSnipUpdateStatus 'checking' '[5/8] Verifying OCR, native capture and the Screenshots folder...' $expectedVersion
        if ($InstallOCR) { & (Join-Path $candidate 'Repair-OCR.ps1') -InstallDir $candidate -PythonExecutable $candidatePython }
        & $candidatePython -m beastsnip.maintenance --check-native
        if ($LASTEXITCODE -ne 0) { throw 'Native monitor/capture validation failed.' }
        & $candidatePython -m beastsnip.maintenance --configure-autosave 'C:\SnipsV1\Screenshots'
        if ($LASTEXITCODE -ne 0) { throw 'The Screenshots folder or preferences could not be prepared.' }
    } finally { Pop-Location }
    Write-BeastSnipUpdateStatus 'activating' '[6/8] Activating the tested application and runtime...' $expectedVersion
    Invoke-BeastSnipActivation -Transaction $transaction -Candidate $candidate
    Clear-BeastSnipBytecode -InstallDir $destination
    Push-Location -LiteralPath $destination
    try {
        $activePython = Get-BeastSnipPython -InstallDir $destination
        $activeWindowed = Get-BeastSnipPython -InstallDir $destination -Windowed
        $installed = & $activePython -c 'import beastsnip; print(beastsnip.__version__)'
        if ($LASTEXITCODE -ne 0 -or ([string]$installed).Trim() -ne $expectedVersion) { throw 'Post-activation version verification failed.' }
        $previousDataDir = $env:BEASTSNIP_DATA_DIR
        $smokeDir = Join-Path ([IO.Path]::GetTempPath()) ('BeastSnip-active-check-' + [guid]::NewGuid().ToString('N'))
        try {
            $env:BEASTSNIP_DATA_DIR = $smokeDir
            & $activePython -m beastsnip --smoke-test
            if ($LASTEXITCODE -ne 0) { throw 'Post-activation startup verification failed.' }
        } finally {
            if ($null -eq $previousDataDir) { Remove-Item Env:BEASTSNIP_DATA_DIR -ErrorAction SilentlyContinue } else { $env:BEASTSNIP_DATA_DIR = $previousDataDir }
            Remove-Item -LiteralPath $smokeDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-BeastSnipUpdateStatus 'activating' '[7/8] Refreshing the desktop shortcut and icon...' $expectedVersion
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $activeWindowed
        $shortcut.Arguments = '"' + (Join-Path $destination 'run_beastsnip.py') + '"'
        $shortcut.WorkingDirectory = $destination
        $shortcut.IconLocation = (Join-Path $destination 'beastsnip/resources/beastsnip.ico') + ',0'
        $shortcut.Description = 'BeastSnip - screenshots, projects and offline OCR'
        $shortcut.Save()
    } finally { Pop-Location }
    $transaction.State = 'complete'
    Save-BeastSnipTransaction $transaction
    $committed = $true
    Write-BeastSnipUpdateStatus 'complete' "[8/8] UPDATE COMPLETE - BeastSnip $expectedVersion" $expectedVersion
    Write-Host "Installed in $destination. Rollback backup: $($transaction.Backup)" -ForegroundColor Green
    if ($Launch) {
        try { & (Join-Path $destination 'Launch.ps1') } catch { Write-Warning ('The update is complete, but automatic launch failed. Use the desktop shortcut. ' + $_.Exception.Message) }
    }
} catch {
    $originalError = $_
    $message = 'UPDATE FAILED: ' + $_.Exception.Message
    if ($transaction -and -not $committed) {
        try {
            Restore-BeastSnipTransaction $transaction
            $message += ' Previous application, runtime selection and settings restored.'
            Write-BeastSnipUpdateStatus 'rolled-back' $message $expectedVersion
        } catch {
            $message += ' Automatic rollback could not finish: ' + $_.Exception.Message + '. Backup: ' + $transaction.Backup
            Write-BeastSnipUpdateStatus 'failed' $message $expectedVersion
        }
    } else { Write-BeastSnipUpdateStatus 'failed' $message $expectedVersion }
    if ($Launch -and $closedPrevious -and -not $committed -and (Test-Path -LiteralPath (Join-Path $destination 'Launch.ps1'))) {
        try { & (Join-Path $destination 'Launch.ps1') } catch { Write-Warning 'The previous app could not be relaunched automatically. Use its desktop shortcut.' }
    }
    throw $originalError
} finally {
    if (-not $committed -and (-not $transaction -or $transaction.State -eq 'rolled-back') -and (Test-Path -LiteralPath $runtimeDir)) { Remove-Item -LiteralPath $runtimeDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Recurse -Force -ErrorAction SilentlyContinue }
    $updateLock.Dispose()
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
