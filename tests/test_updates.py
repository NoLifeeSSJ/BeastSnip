import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from beastsnip.updates import download_update, validate_manifest, version_tuple


def manifest(raw=b'example updater'):
    return {'schema': 1, 'version': '2.1.0', 'notes': ['A tested release'],
            'updater_url': 'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/v2.1.0/delivery/Update-BeastSnip-2.1.0.ps1',
            'updater_sha256': hashlib.sha256(raw).hexdigest()}


class UpdateManifestTests(unittest.TestCase):
    def test_versions_compare_numerically(self):
        self.assertGreater(version_tuple('2.10.0'), version_tuple('2.9.9'))
        for bad in ('2.1', '2.1.0;run', '../2.1.0', None):
            with self.assertRaises(ValueError): version_tuple(bad)

    def test_unexpected_download_hosts_paths_checksums_and_notes_are_rejected(self):
        validate_manifest(manifest())
        for key, value in [('updater_url', 'https://example.com/Update-BeastSnip-2.1.0.ps1'),
                           ('updater_url', 'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/other.ps1'),
                           ('updater_sha256', 'bad'), ('notes', '<script>not notes</script>')]:
            payload = manifest(); payload[key] = value
            with self.assertRaises(ValueError): validate_manifest(payload)

    def test_only_verified_bytes_are_written_and_a_failed_download_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = manifest()
            path = Path(directory) / 'Update-BeastSnip-2.1.0.ps1'
            path.write_bytes(b'previous verified file')
            for raw, fails in [(b'corrupted download', True), (b'example updater', False)]:
                response = io.BytesIO(raw); response.url = payload['updater_url']
                with patch('beastsnip.updates.urllib.request.urlopen', return_value=response):
                    if fails:
                        with self.assertRaises(ValueError): download_update(payload, directory)
                        self.assertEqual(path.read_bytes(), b'previous verified file')
                    else:
                        self.assertEqual(download_update(payload, directory), path)
                        self.assertEqual(path.read_bytes(), raw)
