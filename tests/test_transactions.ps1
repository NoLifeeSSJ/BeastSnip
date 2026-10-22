#Requires -Version 5.1
# Real filesystem transactions; no native process termination or COM operations.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../tools/Install-Transaction.ps1')
$script:transactionChecks = 0
function Assert-TransactionTest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:transactionChecks++
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ("BeastSnip transaction O'Connor-" + [guid]::NewGuid().ToString('N'))
$priorData = $env:BEASTSNIP_DATA_DIR
try {
    $env:BEASTSNIP_DATA_DIR = Join-Path $temporary 'user data'
    New-Item -ItemType Directory -Path $env:BEASTSNIP_DATA_DIR -Force | Out-Null
    $names = @('beastsnip','run_beastsnip.py','README.md','runtime.json')
    foreach ($scenario in @('mid-activation','post-activation','prepared-only','success')) {
        $root = Join-Path $temporary $scenario
        $candidate = Join-Path $root '.stage'
        New-Item -ItemType Directory -Path (Join-Path $root 'beastsnip'), (Join-Path $candidate 'beastsnip'), (Join-Path $root 'Screenshots'), (Join-Path $root '.venv/Scripts') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $root 'beastsnip/version.txt') -Value 'previous'
        Set-Content -LiteralPath (Join-Path $candidate 'beastsnip/version.txt') -Value 'candidate'
        Set-Content -LiteralPath (Join-Path $root 'run_beastsnip.py') -Value 'previous entry'
        Set-Content -LiteralPath (Join-Path $candidate 'run_beastsnip.py') -Value 'candidate entry'
        Set-Content -LiteralPath (Join-Path $root 'README.md') -Value 'previous documentation'
        Set-Content -LiteralPath (Join-Path $candidate 'README.md') -Value 'candidate documentation'
        Set-Content -LiteralPath (Join-Path $root 'Screenshots/keep.png') -Value 'user image'
        Set-Content -LiteralPath (Join-Path $root '.venv/Scripts/python.exe') -Value 'previous runtime'
        $oldRuntime = [guid]::NewGuid().ToString('N')
        $newRuntime = [guid]::NewGuid().ToString('N')
        Write-BeastSnipJson (Join-Path $root 'runtime.json') @{schema=1; runtime=$oldRuntime; version='2.0.1'}
        Write-BeastSnipJson (Join-Path $candidate 'runtime.json') @{schema=1; runtime=$newRuntime; version='2.1.0'}
        $settings = Join-Path $env:BEASTSNIP_DATA_DIR 'settings.json'
        [IO.File]::WriteAllText($settings, '{"ocr_path":"keep.exe","custom":"preserve exactly"}')
        $originalSettings = [IO.File]::ReadAllBytes($settings)
        $transaction = New-BeastSnipTransaction -InstallDir $root -Names $names -Runtime $newRuntime
        Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'beastsnip/version.txt')).Trim() -eq 'previous') 'Preparing an update must not change live application files'
        [IO.File]::WriteAllText($settings, '{"ocr_path":"candidate.exe","auto_save":true}')
        $injected = $false
        try {
            if ($scenario -eq 'mid-activation') {
                Invoke-BeastSnipActivation -Transaction $transaction -Candidate $candidate -AfterEntry { param($name) if ($name -eq 'beastsnip') { throw 'SIMULATED copy/activation failure' } }
            } elseif ($scenario -ne 'prepared-only') {
                Invoke-BeastSnipActivation -Transaction $transaction -Candidate $candidate
                if ($scenario -eq 'post-activation') { throw 'SIMULATED version/startup/shortcut failure' }
            }
        } catch {
            $injected = $_.Exception.Message -match 'SIMULATED'
            if (-not $injected) { throw }
        }
        if ($scenario -ne 'success') {
            if ($scenario -ne 'prepared-only') { Assert-TransactionTest $injected 'Expected failure injection was not observed' }
            Restore-BeastSnipTransaction $transaction
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'beastsnip/version.txt')).Trim() -eq 'previous') 'Previous package was not restored'
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'run_beastsnip.py')).Trim() -eq 'previous entry') 'Previous entry point was not restored'
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'README.md')).Trim() -eq 'previous documentation') 'Previous documentation was not restored'
            Assert-TransactionTest (((Get-Content -Raw -LiteralPath (Join-Path $root 'runtime.json') | ConvertFrom-Json).runtime) -eq $oldRuntime) 'Previous runtime selection was not restored'
            Assert-TransactionTest ([Convert]::ToBase64String([IO.File]::ReadAllBytes($settings)) -eq [Convert]::ToBase64String($originalSettings)) 'Original settings bytes were not restored'
            Restore-BeastSnipTransaction $transaction
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'beastsnip/version.txt')).Trim() -eq 'previous') 'A repeated rollback must not delete the restored package'
        } else {
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'beastsnip/version.txt')).Trim() -eq 'candidate') 'Candidate activation failed'
            Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $transaction.Backup 'beastsnip/version.txt')).Trim() -eq 'previous') 'Successful activation must retain the previous package backup'
            $transaction.State = 'complete'; Save-BeastSnipTransaction $transaction
        }
        Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root 'Screenshots/keep.png')).Trim() -eq 'user image') 'User screenshot was changed'
        Assert-TransactionTest ((Get-Content -LiteralPath (Join-Path $root '.venv/Scripts/python.exe')).Trim() -eq 'previous runtime') 'The previous Python environment was modified'
    }
    $fresh = Join-Path $temporary 'fresh'
    $candidate = Join-Path $fresh '.stage'
    New-Item -ItemType Directory -Path (Join-Path $candidate 'beastsnip') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $candidate 'beastsnip/new.txt') -Value 'candidate only'
    Remove-Item -LiteralPath (Join-Path $env:BEASTSNIP_DATA_DIR 'settings.json')
    $transaction = New-BeastSnipTransaction $fresh @('beastsnip') ([guid]::NewGuid().ToString('N'))
    Invoke-BeastSnipActivation $transaction $candidate
    Set-Content -LiteralPath $transaction.Settings -Value '{"new":true}'
    Restore-BeastSnipTransaction $transaction
    Assert-TransactionTest (-not (Test-Path -LiteralPath (Join-Path $fresh 'beastsnip'))) 'Fresh-install rollback must remove only the new application package'
    Assert-TransactionTest (-not (Test-Path -LiteralPath $transaction.Settings)) 'Fresh-install rollback must remove newly created preferences'
    $malicious = $transaction.PSObject.Copy()
    $malicious.Entries = @([pscustomobject]@{Name='../outside';OldMoved=$false;NewMoved=$false})
    $rejected = $false
    try { Restore-BeastSnipTransaction $malicious } catch { $rejected = $true }
    Assert-TransactionTest $rejected 'Rollback must reject paths outside its application allowlist'
    $legacyRoot = Join-Path $temporary 'legacy runtime'
    New-Item -ItemType Directory -Path (Join-Path $legacyRoot '.venv/Scripts') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $legacyRoot '.venv/Scripts/python.exe') -Value 'legacy'
    Assert-TransactionTest ((Get-BeastSnipPython $legacyRoot) -eq (Join-Path $legacyRoot '.venv/Scripts/python.exe')) 'Legacy Python lookup must remain available'
    Write-BeastSnipJson (Join-Path $legacyRoot 'runtime.json') @{schema=1;runtime='../outside'}
    $rejected = $false
    try { Get-BeastSnipPython $legacyRoot | Out-Null } catch { $rejected=$true }
    Assert-TransactionTest $rejected 'Invalid runtime traversal must be rejected'
    $interruptedRoot = Join-Path $temporary 'interrupted activation'
    New-Item -ItemType Directory -Path (Join-Path $interruptedRoot 'beastsnip') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $interruptedRoot 'beastsnip/old.txt') -Value 'previous'
    $transaction = New-BeastSnipTransaction $interruptedRoot @('beastsnip') ([guid]::NewGuid().ToString('N'))
    $transaction.State = 'activating'
    $transaction.Entries[0].Intent = 'backup'
    Save-BeastSnipTransaction $transaction
    # Emulate interruption after the disk move but before the completion flag.
    Move-Item -LiteralPath (Join-Path $interruptedRoot 'beastsnip') -Destination $transaction.Backup
    New-Item -ItemType Directory -Path (Join-Path $interruptedRoot 'beastsnip') | Out-Null
    Set-Content -LiteralPath (Join-Path $interruptedRoot 'beastsnip/new.txt') -Value 'incomplete candidate'
    function Close-BeastSnipForUpdate { param($InstallDir, [switch]$CloseRunningApp) }
    Repair-BeastSnipInterruptedActivation $interruptedRoot
    Assert-TransactionTest (Test-Path -LiteralPath (Join-Path $interruptedRoot 'beastsnip/old.txt')) 'Interrupted activation must recover from its persisted journal'
    Assert-TransactionTest (-not (Test-Path -LiteralPath (Join-Path $interruptedRoot 'beastsnip/new.txt'))) 'Interrupted candidate files must not survive rollback'
    Repair-BeastSnipInterruptedActivation $interruptedRoot
    Assert-TransactionTest (Test-Path -LiteralPath (Join-Path $interruptedRoot 'beastsnip/old.txt')) 'Repairing an already recovered activation must be harmless'
} finally {
    if ($null -eq $priorData) { Remove-Item Env:BEASTSNIP_DATA_DIR -ErrorAction SilentlyContinue } else { $env:BEASTSNIP_DATA_DIR=$priorData }
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output ("Transaction checks passed: $script:transactionChecks assertions; real files, settings and runtime pointers checked; native installation steps excluded.")
