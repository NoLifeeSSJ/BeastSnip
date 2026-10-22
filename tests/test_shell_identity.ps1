#Requires -Version 5.1
# Compile the real shell interop and check its managed layout, without native calls.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../tools/Shell-Identity.ps1')
Initialize-BeastSnipShellIdentity
if ([BeastSnipShellIdentity]::AppId -ne 'NoLifeeSSJ.BeastSnip.Desktop') { throw 'The shortcut application ID does not match BeastSnip.' }
$python = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../beastsnip/windows.py') -Raw
if ($python -notmatch ([regex]::Escape("APP_USER_MODEL_ID = '" + [BeastSnipShellIdentity]::AppId + "'"))) { throw 'The native app and shortcut use different application identities.' }
if ([Runtime.InteropServices.Marshal]::SizeOf([type][BeastSnipShellIdentity+PropertyKey]) -ne 20) { throw 'Invalid Windows PROPERTYKEY layout.' }
if ([Runtime.InteropServices.Marshal]::SizeOf([type][BeastSnipShellIdentity+PropertyValue]) -ne 24) { throw 'Invalid 64-bit Windows PROPVARIANT layout.' }
Write-Output 'Shell identity: 4 checks passed; real C# interop compiled. Native Windows Shell calls are checked when the shortcut is installed.'
