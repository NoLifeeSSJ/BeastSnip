"""Build an auditable, self-contained PowerShell installer and source ZIP."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / 'beastsnip/__init__.py').read_text()).group(1)
OUT = ROOT / "delivery"
OUT.mkdir(exist_ok=True)
FILES = [
    "Install.ps1", "Update.ps1", "Repair-OCR.ps1", "Launch.ps1", "Launch.cmd", "Build.ps1", "README.md", "VERIFICATION.md", "CHANGELOG.md",
    "requirements.txt", "requirements-build.txt", "run_beastsnip.py", ".gitignore", ".gitattributes",
]
for directory in ("beastsnip", "tests", "tools"):
    FILES.extend(str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / directory).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
stream = io.BytesIO()
with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for filename in sorted(FILES):
        info = zipfile.ZipInfo(filename, (2026, 10, 22, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, (ROOT / filename).read_bytes())
payload = stream.getvalue()
digest = hashlib.sha256(payload).hexdigest()
encoded = base64.b64encode(payload).decode("ascii")
wrapped = "\n".join(encoded[i:i + 120] for i in range(0, len(encoded), 120))
script = r'''#Requires -Version 5.1
# BeastSnip self-contained source installer. No remote-script execution.
# The embedded ZIP contains the same inspectable source as BeastSnip-source.zip.
[CmdletBinding()]
param(
    [string]$InstallDir = 'C:\SnipV1',
    __OCR_PARAMETER__
    [switch]$CloseRunningApp,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this installer on Windows 11.' }
$logRoot = Join-Path $env:LOCALAPPDATA 'BeastSnip\update-logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$logPath = Join-Path $logRoot ('Update-__VERSION__-' + [guid]::NewGuid().ToString('N') + '.log')
$transcribing = $false
$completed = $false
try {
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
    $transcribing = $true
} catch { Write-Warning 'Transcript logging is unavailable; progress and failures will still be shown below.' }
Write-Host 'BeastSnip __VERSION__ repair/update' -ForegroundColor Cyan
Write-Host "Install folder: $InstallDir"
if ($transcribing) { Write-Host "Update log: $logPath" }
$payload = @'
__PAYLOAD__
'@
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('BeastSnip-setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $archive = Join-Path $temporary 'BeastSnip.zip'
    [IO.File]::WriteAllBytes($archive, [Convert]::FromBase64String($payload))
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '__DIGEST__') {
        throw 'The embedded BeastSnip payload failed its SHA256 integrity check. Download the installer again.'
    }
    $source = Join-Path $temporary 'source'
    Expand-Archive -LiteralPath $archive -DestinationPath $source
    __RUN__
    $completed = $true
} catch {
    Write-Host ('UPDATE FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    if ($transcribing) { Write-Host "Details: $logPath" -ForegroundColor Yellow }
    throw
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
    if (-not $completed) { Write-Host 'UPDATE NOT COMPLETED. Do not expect the previous errors to be fixed yet.' -ForegroundColor Yellow }
    if ($transcribing) { Stop-Transcript | Out-Null }
}
'''
script = script.replace("__PAYLOAD__", wrapped).replace("__DIGEST__", digest.upper()).replace("__VERSION__", VERSION)
installer = OUT / "Setup-BeastSnip.ps1"
updater = OUT / "Update-BeastSnip.ps1"
installer.write_text(script.replace("__OCR_PARAMETER__", "[switch]$InstallOCR,").replace("__RUN__", "& (Join-Path $source 'Install.ps1') -InstallDir $InstallDir -InstallOCR:$InstallOCR -CloseRunningApp:$CloseRunningApp -Launch:$Launch"), encoding="utf-8", newline="\n")
updater.write_text(script.replace("    __OCR_PARAMETER__\n", "").replace("__RUN__", "& (Join-Path $source 'Update.ps1') -InstallDir $InstallDir -CloseRunningApp:$CloseRunningApp -Launch:$Launch"), encoding="utf-8", newline="\n")
repair = OUT / f"Repair-BeastSnip-{VERSION}.ps1"
repair.write_bytes(updater.read_bytes())
versioned_update = OUT / f"Update-BeastSnip-{VERSION}.ps1"
versioned_update.write_bytes(updater.read_bytes())
(OUT / "BeastSnip-source.zip").write_bytes(payload)
section = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').split('## ' + VERSION + ' ', 1)[1].split('\n## ', 1)[0]
notes = [line[2:].strip() for line in section.splitlines() if line.startswith('- ')]
if not notes:
    raise ValueError('The release must include notes in CHANGELOG.md.')
manifest = OUT / 'latest.json'
manifest.write_text(json.dumps({'schema': 1, 'version': VERSION,
    'updater_url': f'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/v{VERSION}/delivery/{versioned_update.name}',
    'updater_sha256': hashlib.sha256(versioned_update.read_bytes()).hexdigest(),
    'notes': notes}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
(OUT / "SHA256SUMS.txt").write_text("\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in (installer, updater, versioned_update, repair, OUT / "BeastSnip-source.zip", manifest)) + "\n", encoding="ascii")
print(f"Created setup/updater scripts and source ZIP ({len(payload):,} bytes).")
