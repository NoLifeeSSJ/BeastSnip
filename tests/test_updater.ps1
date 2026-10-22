#Requires -Version 5.1
# Updater tests. Win32 process operations are mocked; cache tests use real temporary files.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\tools\Update-Helpers.ps1')
$script:checks = 0
function Assert-UpdateTest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:checks++
}
function New-TestProcess {
    param([int]$Number, [string]$Name, [string]$Executable, [string]$Command)
    [pscustomobject]@{ ProcessId=$Number; Name=$Name; ExecutablePath=$Executable; CommandLine=$Command; CreationDate=[datetime]'2026-10-21T20:00:00Z' }
}
$root = 'C:\SnipV1'
$basePython = 'C:\Users\Turlough O''Connor\Python312\pythonw.exe'
$cases = @(
    @((New-TestProcess 1 'pythonw.exe' $basePython ('"' + $basePython + '" "C:\SnipV1\run_beastsnip.py"')), $true),
    @((New-TestProcess 2 'python.exe' 'C:\Python312\python.exe' 'python.exe C:\SnipV1\run_beastsnip.py'), $true),
    @((New-TestProcess 3 'python.exe' 'C:\SnipV1\.venv\Scripts\python.exe' 'python.exe -m beastsnip'), $true),
    @((New-TestProcess 4 'pythonw.exe' 'C:\SnipV1\.venv\Scripts\pythonw.exe' 'pythonw.exe run_beastsnip.py'), $true),
    @((New-TestProcess 5 'BeastSnip.exe' 'C:\SnipV1\dist\BeastSnip\BeastSnip.exe' ''), $true),
    @((New-TestProcess 6 'BeastSnip.exe' 'C:\SnipV1\BeastSnip.exe' ''), $true),
    @((New-TestProcess 7 'pythonw.exe' $basePython 'pythonw.exe C:\Other\run_beastsnip.py'), $false),
    @((New-TestProcess 8 'python.exe' 'C:\Other\.venv\python.exe' 'python.exe -m beastsnip'), $false),
    @((New-TestProcess 9 'python.exe' 'C:\Python312\python.exe' 'python.exe C:\Other\helper.py C:\SnipV1\run_beastsnip.py'), $false),
    @((New-TestProcess 10 'python.exe' 'C:\Python312\python.exe' 'python.exe -c "print(''C:\SnipV1\run_beastsnip.py'')"'), $false),
    @((New-TestProcess 11 'python.exe' 'C:\Python312\python.exe' 'python.exe C:\SnipV10\run_beastsnip.py'), $false),
    @((New-TestProcess 12 'python.exe' 'C:\Python312\python.exe' 'python.exe C:\SnipV1\run_beastsnip.py.bak'), $false),
    @((New-TestProcess 13 'BeastSnip.exe' 'C:\Other\BeastSnip.exe' ''), $false),
    @((New-TestProcess 14 'python.exe' '' ''), $false),
    @((New-TestProcess 15 'other.exe' 'C:\SnipV1\other.exe' 'other.exe C:\SnipV1\run_beastsnip.py'), $false),
    @((New-TestProcess 17 'python.exe' 'C:\SnipV1\.beastsnip-runtimes\0123456789abcdef0123456789abcdef\Scripts\python.exe' 'python.exe -m beastsnip'), $true),
    @((New-TestProcess 18 'pythonw.exe' 'C:\Other\.beastsnip-runtimes\0123456789abcdef0123456789abcdef\Scripts\pythonw.exe' 'pythonw.exe -m beastsnip'), $false),
    @((New-TestProcess 19 'python.exe' 'C:\SnipV1\.beastsnip-runtimes\0123456789abcdef0123456789abcdef\Scripts\python.exe' 'python.exe -m other_module'), $false)
)
foreach ($case in $cases) {
    Assert-UpdateTest ((Test-BeastSnipProcess -Process $case[0] -InstallDir $root) -eq $case[1]) ('Wrong process classification: ' + $case[0].ProcessId)
}
$spaced = New-TestProcess 16 'pythonw.exe' $basePython ('"' + $basePython + '" "C:\My Apps\SnipV1\run_beastsnip.py"')
Assert-UpdateTest (Test-BeastSnipProcess -Process $spaced -InstallDir 'C:\My Apps\SnipV1') 'Paths with spaces/apostrophes must work'

function Reset-ProcessFixture {
    $script:live = @($cases[0][0], $cases[2][0], $cases[6][0], $cases[8][0])
    $script:stopped = @()
    $script:recycled = $false
    $script:denyStop = $false
    $script:ignoreStop = $false
}
function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName, [string]$Filter)
    if ($Filter -match '^ProcessId = (\d+)$') {
        $number = [int]$Matches[1]
        $found = $script:live | Where-Object { $_.ProcessId -eq $number }
        if ($found -and $script:recycled) {
            $copy = $found.PSObject.Copy()
            $copy.CreationDate = $copy.CreationDate.AddSeconds(1)
            return $copy
        }
        return $found
    }
    return $script:live
}
function Stop-Process {
    [CmdletBinding()]
    param([int]$Id, [switch]$Force)
    if ($script:denyStop) { throw 'Simulated access denied' }
    $script:stopped += $Id
    if (-not $script:ignoreStop) { $script:live = @($script:live | Where-Object { $_.ProcessId -ne $Id }) }
}
function Wait-Process {
    [CmdletBinding()]
    param([int]$Id, [int]$Timeout)
}
Reset-ProcessFixture
$message = ''
try { Close-BeastSnipForUpdate -InstallDir $root } catch { $message=$_.Exception.Message }
Assert-UpdateTest ($message -match '-CloseRunningApp') 'Default update must explain how to continue'
Assert-UpdateTest ($script:stopped.Count -eq 0) 'Default update must not stop anything'
Close-BeastSnipForUpdate -InstallDir $root -CloseRunningApp
Assert-UpdateTest (($script:stopped -join ',') -eq '1,3') 'Only target-install BeastSnip processes should stop'
Assert-UpdateTest (($script:live.ProcessId -join ',') -eq '7,9') 'Unrelated Python processes must remain running'
Close-BeastSnipForUpdate -InstallDir $root -CloseRunningApp
Assert-UpdateTest ($script:stopped.Count -eq 2) 'Rerunning after closure must be harmless'
Reset-ProcessFixture
$script:recycled = $true
$message = ''
try { Close-BeastSnipForUpdate -InstallDir $root -CloseRunningApp } catch { $message=$_.Exception.Message }
Assert-UpdateTest ($message -match 'changed') 'PID reuse must be rejected'
Assert-UpdateTest ($script:stopped.Count -eq 0) 'A recycled PID must not be stopped'
Reset-ProcessFixture
$script:denyStop = $true
$message = ''
try { Close-BeastSnipForUpdate -InstallDir $root -CloseRunningApp } catch { $message=$_.Exception.Message }
Assert-UpdateTest ($message -match 'Cannot close BeastSnip') 'Access denial must stop the update'
Reset-ProcessFixture
$script:ignoreStop = $true
$message = ''
try { Close-BeastSnipForUpdate -InstallDir $root -CloseRunningApp } catch { $message=$_.Exception.Message }
Assert-UpdateTest ($message -match 'still running') 'A still-running process must block file replacement'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('BeastSnip-cache-test-' + [guid]::NewGuid().ToString('N'))
try {
    foreach ($directory in @('beastsnip/__pycache__', 'beastsnip/nested/__pycache__', 'history', '.venv')) {
        New-Item -ItemType Directory -Path (Join-Path $temporary $directory) -Force | Out-Null
    }
    foreach ($name in @('beastsnip/__pycache__/__init__.cpython-312.pyc', 'beastsnip/nested/__pycache__/module.cpython-312.pyc',
                       'settings.json', 'history/keep.png', '.venv/keep.pyc', 'beastsnip/keep.pyc', 'beastsnip/__pycache__/notes.txt')) {
        Set-Content -LiteralPath (Join-Path $temporary $name) -Value 'keep unless generated bytecode'
    }
    Clear-BeastSnipBytecode -InstallDir $temporary
    Assert-UpdateTest (-not (Test-Path -LiteralPath (Join-Path $temporary 'beastsnip/__pycache__/__init__.cpython-312.pyc'))) 'Old version cache was not removed'
    Assert-UpdateTest (-not (Test-Path -LiteralPath (Join-Path $temporary 'beastsnip/nested/__pycache__/module.cpython-312.pyc'))) 'Nested module cache was not removed'
    foreach ($name in @('settings.json', 'history/keep.png', '.venv/keep.pyc', 'beastsnip/keep.pyc', 'beastsnip/__pycache__/notes.txt')) {
        Assert-UpdateTest ((Get-Content -LiteralPath (Join-Path $temporary $name)).Trim() -eq 'keep unless generated bytecode') ('Unrelated file was changed: ' + $name)
    }
    Clear-BeastSnipBytecode -InstallDir $temporary
    Assert-UpdateTest (Test-Path -LiteralPath (Join-Path $temporary 'settings.json')) 'Cache cleanup must be repeatable'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
Write-Output ("Updater checks passed: $script:checks assertions; Windows process operations mocked; bytecode files checked on disk.")
