# Atomic metadata, a separate candidate runtime, and reversible application activation.
# Loading this file performs no installation work.
function Write-BeastSnipJson {
    param([string]$Path, [object]$Value)
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = $Path + '.tmp-' + [guid]::NewGuid().ToString('N')
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [System.Management.Automation.Language.NullString]::Value) } else { [IO.File]::Move($temporary, $Path) }
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function Get-BeastSnipDataRoot {
    if ($env:BEASTSNIP_DATA_DIR) { return [IO.Path]::GetFullPath($env:BEASTSNIP_DATA_DIR) }
    return Join-Path $env:LOCALAPPDATA 'BeastSnip'
}

function Write-BeastSnipUpdateStatus {
    param([string]$State, [string]$Message, [string]$Version)
    try {
        Write-BeastSnipJson -Path (Join-Path (Get-BeastSnipDataRoot) 'updates/status.json') -Value @{
            schema=1; state=$State; message=$Message; version=$Version; updated=[datetime]::UtcNow.ToString('o')
        }
    } catch { Write-Warning ('Update status could not be saved: ' + $_.Exception.Message) }
    Write-Host $Message -ForegroundColor Cyan
}

function Get-BeastSnipPython {
    param([string]$InstallDir, [switch]$Windowed)
    $name = if ($Windowed) { 'pythonw.exe' } else { 'python.exe' }
    $active = Join-Path $InstallDir 'runtime.json'
    if (Test-Path -LiteralPath $active) {
        $record = Get-Content -LiteralPath $active -Raw | ConvertFrom-Json
        if ($record.schema -ne 1 -or [string]$record.runtime -notmatch '^[a-f0-9]{32}$') { throw 'The active runtime record is invalid. Rerun the full updater.' }
        $path = Join-Path (Join-Path (Join-Path $InstallDir '.beastsnip-runtimes') $record.runtime) ('Scripts/' + $name)
    } else {
        $path = Join-Path $InstallDir ('.venv/Scripts/' + $name)
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'The BeastSnip Python runtime is missing. Run the full PowerShell updater.' }
    return $path
}

function Save-BeastSnipTransaction {
    param([object]$Transaction)
    Write-BeastSnipJson -Path (Join-Path $Transaction.Backup 'transaction.json') -Value $Transaction
}

function New-BeastSnipTransaction {
    param([string]$InstallDir, [string[]]$Names, [string]$Runtime, [string]$ShortcutPath='')
    if (-not $Names.Count -or $Runtime -notmatch '^[a-f0-9]{32}$' -or @($Names | Where-Object { $_ -notmatch '^[a-zA-Z0-9_.-]+$' -or $_ -in @('.', '..') }).Count) {
        throw 'Invalid transaction paths.'
    }
    $root = [IO.Path]::GetFullPath($InstallDir)
    $backup = Join-Path (Join-Path $root '.beastsnip-backups') ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    $settings = Join-Path (Get-BeastSnipDataRoot) 'settings.json'
    $transaction = [pscustomobject]@{
        Schema=1; Root=$root; Backup=$backup; Runtime=$Runtime; State='prepared';
        Settings=$settings; SettingsExisted=(Test-Path -LiteralPath $settings);
        Shortcut=$ShortcutPath; ShortcutExisted=($ShortcutPath -and (Test-Path -LiteralPath $ShortcutPath));
        Entries=@($Names | ForEach-Object { [pscustomobject]@{ Name=$_; Existed=(Test-Path -LiteralPath (Join-Path $root $_)); OldMoved=$false; NewMoved=$false; Restored=$false; Intent='' } })
    }
    if ($transaction.SettingsExisted) { Copy-Item -LiteralPath $settings -Destination (Join-Path $backup 'previous-settings.json') -Force }
    if ($transaction.ShortcutExisted) { Copy-Item -LiteralPath $ShortcutPath -Destination (Join-Path $backup 'previous-shortcut.lnk') -Force }
    Save-BeastSnipTransaction $transaction
    return $transaction
}

function Test-BeastSnipTransaction {
    param([object]$Transaction)
    $root = [IO.Path]::GetFullPath($Transaction.Root)
    $expected = Join-Path $root '.beastsnip-backups'
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($Transaction.Backup))
    if ($Transaction.Schema -ne 1 -or $Transaction.Runtime -notmatch '^[a-f0-9]{32}$' -or $parent -ne $expected -or
        $Transaction.Settings -ne (Join-Path (Get-BeastSnipDataRoot) 'settings.json')) { throw 'The rollback record is invalid.' }
    $allowed = @('beastsnip','tests','tools','run_beastsnip.py','requirements.txt','requirements-build.txt','Install.ps1','Update.ps1','Repair-OCR.ps1','Launch.ps1','Launch.cmd','Build.ps1','README.md','VERIFICATION.md','CHANGELOG.md','runtime.json')
    if (@($Transaction.Entries | Where-Object { $_.Name -notin $allowed }).Count) { throw 'The rollback record contains unsupported paths.' }
    if ($Transaction.Shortcut) {
        $expectedShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'BeastSnip.lnk'
        if ($Transaction.Shortcut -ne $expectedShortcut) { throw 'The rollback shortcut path is invalid.' }
    }
}

function Invoke-BeastSnipActivation {
    param([object]$Transaction, [string]$Candidate, [scriptblock]$AfterEntry)
    Test-BeastSnipTransaction $Transaction
    if ($Transaction.State -ne 'prepared') { throw 'This transaction is not ready for activation.' }
    $Transaction.State = 'activating'
    Save-BeastSnipTransaction $Transaction
    foreach ($entry in $Transaction.Entries) {
        $destination = Join-Path $Transaction.Root $entry.Name
        $source = Join-Path $Candidate $entry.Name
        if (-not (Test-Path -LiteralPath $source)) { throw ('The candidate is missing ' + $entry.Name) }
        $entry.Intent = 'backup'
        Save-BeastSnipTransaction $Transaction
        if (Test-Path -LiteralPath $destination) {
            Move-Item -LiteralPath $destination -Destination (Join-Path $Transaction.Backup $entry.Name) -Force
            $entry.OldMoved = $true
        }
        $entry.Intent = 'install'
        Save-BeastSnipTransaction $Transaction
        Move-Item -LiteralPath $source -Destination $destination -Force
        $entry.NewMoved = $true
        $entry.Intent = ''
        Save-BeastSnipTransaction $Transaction
        if ($AfterEntry) { & $AfterEntry $entry.Name }
    }
    $Transaction.State = 'checking'
    Save-BeastSnipTransaction $Transaction
}

function Restore-BeastSnipTransaction {
    param([object]$Transaction)
    Test-BeastSnipTransaction $Transaction
    if ($Transaction.State -eq 'rolled-back') { return }
    $Transaction.State = 'rolling-back'
    Save-BeastSnipTransaction $Transaction
    foreach ($entry in @($Transaction.Entries)[($Transaction.Entries.Count - 1)..0]) {
        $destination = Join-Path $Transaction.Root $entry.Name
        $backup = Join-Path $Transaction.Backup $entry.Name
        # Intent is persisted before each same-volume move, so an interrupted
        # activation can also be repaired by the next updater invocation.
        if ($entry.Restored) { continue }
        if (Test-Path -LiteralPath $backup) {
            if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }
            Move-Item -LiteralPath $backup -Destination $destination -Force
        } elseif (-not $entry.Existed -and ($entry.NewMoved -or $entry.Intent -eq 'install') -and (Test-Path -LiteralPath $destination)) {
            Remove-Item -LiteralPath $destination -Recurse -Force
        } elseif ($entry.Existed -and -not (Test-Path -LiteralPath $destination)) {
            throw ('The previous file is missing from both the live installation and backup: ' + $entry.Name)
        }
        $entry.Restored = $true
        Save-BeastSnipTransaction $Transaction
    }
    if ($Transaction.SettingsExisted) {
        Copy-Item -LiteralPath (Join-Path $Transaction.Backup 'previous-settings.json') -Destination $Transaction.Settings -Force
    } elseif (Test-Path -LiteralPath $Transaction.Settings) { Remove-Item -LiteralPath $Transaction.Settings -Force }
    if ($Transaction.Shortcut) {
        if ($Transaction.ShortcutExisted) {
            Copy-Item -LiteralPath (Join-Path $Transaction.Backup 'previous-shortcut.lnk') -Destination $Transaction.Shortcut -Force
        } elseif (Test-Path -LiteralPath $Transaction.Shortcut) { Remove-Item -LiteralPath $Transaction.Shortcut -Force }
    }
    $Transaction.State = 'rolled-back'
    Save-BeastSnipTransaction $Transaction
}

function Repair-BeastSnipInterruptedActivation {
    param([string]$InstallDir)
    $backups = Join-Path $InstallDir '.beastsnip-backups'
    if (-not (Test-Path -LiteralPath $backups)) { return }
    foreach ($file in Get-ChildItem -LiteralPath $backups -Filter 'transaction.json' -File -Recurse) {
        $transaction = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
        if ($transaction.Root -ne [IO.Path]::GetFullPath($InstallDir)) { throw 'An interrupted update record has an unexpected installation path.' }
        if ($transaction.State -in @('prepared','activating','checking','rolling-back')) {
            Close-BeastSnipForUpdate -InstallDir $InstallDir -CloseRunningApp
            Restore-BeastSnipTransaction $transaction
            Write-Host 'Restored the interrupted application activation.' -ForegroundColor Yellow
        }
    }
}
