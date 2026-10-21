# Helpers shared by the installer and updater. This file performs no work when loaded.
function Clear-BeastSnipBytecode {
    [CmdletBinding()]
    param([string]$InstallDir)
    $package = Join-Path $InstallDir 'beastsnip'
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { return }
    # ZIP entries have deterministic timestamps. Equal-size source changes can
    # otherwise leave an older timestamp-based .pyc looking valid to Python.
    Get-ChildItem -LiteralPath $package -Recurse -File -Filter '*.pyc' -ErrorAction Stop |
        Where-Object { $_.Directory.Name -eq '__pycache__' } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop }
    Write-Host 'Cleared generated BeastSnip bytecode caches.'
}

function Test-BeastSnipProcess {
    [CmdletBinding()]
    param([object]$Process, [string]$InstallDir)
    $root = $InstallDir.Replace('/', '\').TrimEnd('\')
    $executable = [string]$Process.ExecutablePath
    $executable = $executable.Replace('/', '\')
    if ([string]::Equals([string]$Process.Name, 'BeastSnip.exe', [StringComparison]::OrdinalIgnoreCase)) {
        return ([string]::Equals($executable, ($root + '\dist\BeastSnip\BeastSnip.exe'), [StringComparison]::OrdinalIgnoreCase) -or
                [string]::Equals($executable, ($root + '\BeastSnip.exe'), [StringComparison]::OrdinalIgnoreCase))
    }
    if ([string]$Process.Name -notmatch '^(?i:pythonw?\.exe)$') { return $false }
    $commandLine = [string]$Process.CommandLine
    if (-not $commandLine) { return $false }
    $entry = [regex]::Escape($root + '\run_beastsnip.py')
    # Require the actual script argument, not a path embedded inside -c code or
    # an unrelated script's arguments. Do not stop arbitrary Python processes.
    $prefix = '^\s*(?:"[^"]+"|\S+)\s+(?:(?:-[uBEIsSO]+|-OO|-X\s+\S+|-W\s+\S+)\s+)*'
    if ($commandLine -match ($prefix + '(?:"' + $entry + '"|' + $entry + ')(?:\s|$)')) { return $true }
    if ($executable.StartsWith(($root + '\.venv\'), [StringComparison]::OrdinalIgnoreCase)) {
        return ($commandLine -match ($prefix + '(?:-m\s+beastsnip|"?run_beastsnip\.py"?)(?:\s|$)'))
    }
    return $false
}

function Get-BeastSnipProcesses {
    [CmdletBinding()]
    param([string]$InstallDir)
    Get-CimInstance -ClassName Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'BeastSnip.exe'" -ErrorAction Stop |
        Where-Object { Test-BeastSnipProcess -Process $_ -InstallDir $InstallDir }
}

function Close-BeastSnipForUpdate {
    [CmdletBinding()]
    param([string]$InstallDir, [switch]$CloseRunningApp)
    $running = @(Get-BeastSnipProcesses -InstallDir $InstallDir)
    if ($running.Count -eq 0) {
        Write-Host 'BeastSnip is closed. Continuing the update.'
        return
    }
    if (-not $CloseRunningApp) {
        throw 'UPDATE HAS NOT STARTED: BeastSnip is running. Save your capture, then rerun with -CloseRunningApp, or use tray > Quit BeastSnip. No application files were replaced.'
    }
    Write-Host 'Closing BeastSnip for the requested update. Unsaved edits will be discarded; saved history and exports are retained.' -ForegroundColor Yellow
    foreach ($candidate in $running) {
        $targetProcessId = [int]$candidate.ProcessId
        # Recheck identity immediately before stopping it, including creation
        # time, so a recycled PID cannot target a different process.
        $current = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $targetProcessId" -ErrorAction Stop
        if ($null -eq $current) { continue }
        if (-not (Test-BeastSnipProcess -Process $current -InstallDir $InstallDir) -or $null -eq $current.CreationDate -or $current.CreationDate -ne $candidate.CreationDate) {
            throw 'The running process changed during the update check. Nothing was stopped for that PID. Rerun the updater.'
        }
        try {
            Stop-Process -Id $targetProcessId -Force -ErrorAction Stop
            Wait-Process -Id $targetProcessId -Timeout 15 -ErrorAction SilentlyContinue
        } catch {
            throw "Cannot close BeastSnip process $targetProcessId. Quit it from its tray menu, then rerun the updater. $($_.Exception.Message)"
        }
    }
    if (@(Get-BeastSnipProcesses -InstallDir $InstallDir).Count -ne 0) {
        throw 'BeastSnip is still running. No application files have been replaced. Quit it from the tray and rerun the updater.'
    }
    Write-Host 'BeastSnip stopped. Applying the update now.' -ForegroundColor Green
}
