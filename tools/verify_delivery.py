"""Check the published installer payload, source files, manifest and checksums."""
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'delivery'
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / 'beastsnip/__init__.py').read_text()).group(1)


def verify():
    payload = (OUT / 'BeastSnip-source.zip').read_bytes()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.testzip() is None, 'A source ZIP entry failed its CRC check'
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename
            assert archive.read(info.filename) == (ROOT / info.filename).read_bytes(), 'Outdated payload: ' + info.filename
    for name in ['Setup-BeastSnip.ps1', 'Update-BeastSnip.ps1', f'Update-BeastSnip-{VERSION}.ps1', f'Repair-BeastSnip-{VERSION}.ps1']:
        script = (OUT / name).read_text(encoding='utf-8')
        embedded = base64.b64decode(re.search(r"\$payload = @'\n(.*?)\n'@", script, re.S).group(1))
        assert embedded == payload, 'Embedded ZIP differs: ' + name
        expected = re.search(r"\.Hash -ne '([A-F0-9]{64})'", script).group(1)
        assert hashlib.sha256(embedded).hexdigest().upper() == expected
        assert 'BeastSnip ' + VERSION + ' repair/update' in script
    manifest = json.loads((OUT / 'latest.json').read_text(encoding='utf-8'))
    assert manifest['schema'] == 1 and manifest['version'] == VERSION
    assert manifest['updater_url'] == f'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/v{VERSION}/delivery/Update-BeastSnip-{VERSION}.ps1'
    assert manifest['notes']
    assert manifest['updater_sha256'] == hashlib.sha256((OUT / f'Update-BeastSnip-{VERSION}.ps1').read_bytes()).hexdigest()
    for line in (OUT / 'SHA256SUMS.txt').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == checksum, 'Checksum mismatch: ' + name
    print(f'BeastSnip {VERSION}: ZIP CRC/paths/source, four embedded payloads, release manifest and delivery checksums verified.')


if __name__ == '__main__':
    verify()
