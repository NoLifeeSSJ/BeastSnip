import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from beastsnip import maintenance
from beastsnip.config import Settings
from beastsnip.ocr import find_tesseract, find_tessdata, recognize
from test_document import APP, white_image


class OCRRepairTests(unittest.TestCase):
    def test_per_user_programs_install_found_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Programs/Tesseract-OCR/tesseract.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=True), patch("beastsnip.ocr.shutil.which", return_value=None):
                # Other installed runtimes must not mask this specific candidate.
                with patch("beastsnip.ocr.registry_tesseract_paths", return_value=[]):
                    self.assertEqual(find_tesseract(), str(executable))

    def test_registry_install_and_quoted_custom_path_found(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "custom folder/tesseract.exe"
            executable.parent.mkdir()
            executable.touch()
            with patch("beastsnip.ocr.shutil.which", return_value=None), patch("beastsnip.ocr.registry_tesseract_paths", return_value=[str(executable)]), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(find_tesseract(), str(executable))
                self.assertEqual(find_tesseract('"' + str(executable) + '"'), str(executable))

    def test_explicit_language_directory_overrides_broken_environment_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "eng.traineddata").touch()
            with patch.dict(os.environ, {"TESSDATA_PREFIX": "/missing/location"}):
                self.assertEqual(find_tessdata("tesseract", "eng", directory), directory)

    def test_missing_language_has_specific_error_before_image_is_sent(self):
        listing = subprocess.CompletedProcess([], 0, b'List of available languages (1):\neng\n', b'')
        with patch("beastsnip.ocr.find_tessdata", return_value=""), patch("beastsnip.ocr.subprocess.run", return_value=listing) as run:
            with self.assertRaisesRegex(RuntimeError, "deu"):
                recognize(white_image(), "tesseract", "eng+deu")
            run.assert_called_once()
            self.assertNotIn("input", run.call_args.kwargs)

    def test_language_download_checksum_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eng.traineddata"
            path.write_bytes(b'previous language file')
            response = io.BytesIO(b'x' * 2000)
            response.url = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/test/eng.traineddata"
            with patch("beastsnip.maintenance.urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    maintenance.download_language("eng", directory)
            self.assertEqual(path.read_bytes(), b'previous language file')

    def test_repair_merges_ocr_paths_preserving_settings_and_makes_backup(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BEASTSNIP_DATA_DIR": directory}):
            path = Path(directory) / "settings.json"
            before = {"history_dir": "custom-history", "save_dir": "my-pictures", "auto_history": False,
                      "hotkey": "Ctrl+Alt+X", "ocr_language": "eng+deu", "unknown_preference": 42}
            path.write_text(json.dumps(before))
            with patch.object(maintenance, "tesseract_candidates", return_value=["Tesseract.exe"]), patch.object(maintenance, "check_runtime"), patch.object(maintenance, "prepare_tessdata", return_value="languages"), patch.object(maintenance, "check_ocr"):
                maintenance.repair_ocr()
            result = json.loads(path.read_text())
            for key, value in before.items():
                self.assertEqual(result[key], value)
            self.assertEqual(result["ocr_path"], "Tesseract.exe")
            self.assertEqual(result["ocr_data_dir"], "languages")
            backups = list(Path(directory).glob("settings.ocr-backup-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text()), before)

    def test_failed_recognition_never_overwrites_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BEASTSNIP_DATA_DIR": directory}):
            path = Path(directory) / "settings.json"
            path.write_text('{"hotkey":"Ctrl+Alt+X"}')
            original = path.read_bytes()
            with patch.object(maintenance, "tesseract_candidates", return_value=["Tesseract.exe"]), patch.object(maintenance, "check_runtime"), patch.object(maintenance, "prepare_tessdata", return_value="languages"), patch.object(maintenance, "check_ocr", side_effect=RuntimeError("recognition failed")):
                with self.assertRaisesRegex(RuntimeError, "recognition failed"):
                    maintenance.repair_ocr()
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
