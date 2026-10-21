"""Local update diagnostics and OCR repair; never uploads images or OCR text."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import uuid

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from .config import Settings, atomic_bytes, data_dir
from .ocr import (find_tesseract, language_codes, process_options,
                  recognize, tessdata_candidates, tesseract_candidates)
from . import windows


TESSDATA_COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
ENGLISH_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"


class RuntimeFailure(RuntimeError):
    pass


def check_runtime(executable):
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, **process_options())
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("Tesseract cannot start. Repair/reinstall its Windows runtime (including required DLLs).") from error
    if result.returncode or b"tesseract" not in result.stdout.lower():
        raise RuntimeFailure("The selected executable did not start as Tesseract. Repair/reinstall its Windows runtime.")


def download_language(code, directory):
    language_codes(code)
    directory = Path(directory)
    target = directory / f"{code}.traineddata"
    if code == "eng" and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == ENGLISH_SHA256:
        return
    url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{TESSDATA_COMMIT}/{code}.traineddata"
    print(f"Preparing local OCR language: {code}", flush=True)
    # Default HTTPS certificate verification stays enabled. Only static model
    # files are downloaded from a pinned official repository commit.
    with urllib.request.urlopen(url, timeout=60) as response:
        if not response.url.startswith("https://raw.githubusercontent.com/"):
            raise RuntimeError("The language download redirected outside its trusted HTTPS source.")
        content = response.read(128 * 1024 * 1024 + 1)
    if len(content) < 1000 or len(content) > 128 * 1024 * 1024:
        raise RuntimeError(f"The downloaded {code} language file has an unexpected size.")
    if code == "eng" and hashlib.sha256(content).hexdigest() != ENGLISH_SHA256:
        raise RuntimeError("English OCR language checksum failed. The existing language file was left unchanged.")
    if target.exists():
        backup = data_dir() / "ocr" / "backups" / f"{code}-{uuid.uuid4().hex}.traineddata"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    atomic_bytes(target, content)


def prepare_tessdata(executable, languages, configured="", force=False):
    codes = language_codes(languages)
    if not force:
        for directory in tessdata_candidates(executable, configured):
            if all((directory / f"{code}.traineddata").is_file() for code in set(codes + ["eng"])):
                return str(directory)
    managed = data_dir() / "ocr" / "tessdata"
    for code in dict.fromkeys(["eng"] + codes):
        download_language(code, managed)
    return str(managed)


def synthetic_ocr_image():
    image = QImage(1000, 180, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    font = QFont("Arial")
    font.setPixelSize(62)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(QRectF(20, 15, 960, 145), Qt.AlignmentFlag.AlignCenter, "BEASTSNIP LOCAL 2468")
    painter.end()
    return image


def check_ocr(executable, directory, languages):
    image = synthetic_ocr_image()
    text = recognize(image, executable, "eng", directory)
    if "2468" not in text or "LOCAL" not in text.upper():
        raise RuntimeError("The offline OCR recognition check did not read the generated test image.")
    if languages != "eng":
        recognize(image, executable, languages, directory)
    # Verify opaque pixels, not hidden source text, are sent for recognition.
    image.fill(QColor("black"))
    if recognize(image, executable, "eng", directory).strip():
        raise RuntimeError("The opaque-image OCR privacy check did not pass.")


def repair_ocr():
    settings = Settings()
    executable, broken = None, False
    for candidate in dict.fromkeys(tesseract_candidates(settings["ocr_path"])):
        try:
            check_runtime(candidate)
            executable = candidate
            break
        except RuntimeFailure:
            broken = True
    if executable is None:
        if broken:
            raise RuntimeFailure("Found Tesseract, but none of its executables could start. Repair/reinstall the Windows runtime.")
        raise RuntimeError("Tesseract is not installed. Run Repair-OCR.ps1 to install the runtime.")
    languages = settings["ocr_language"]
    directory = prepare_tessdata(executable, languages, settings["ocr_data_dir"])
    try:
        check_ocr(executable, directory, languages)
    except RuntimeError:
        # Existing/corrupt trained data is a different diagnosis: retry once
        # using fresh app-managed files, preserving the runtime's originals.
        directory = prepare_tessdata(executable, languages, force=True)
        check_ocr(executable, directory, languages)
    if settings.path.exists():
        original = json.loads(settings.path.read_text(encoding="utf-8"))
        if not isinstance(original, dict):
            raise ValueError("Settings are not a JSON object; the original file was left unchanged.")
        backup = settings.path.with_name("settings.ocr-backup-" + uuid.uuid4().hex + ".json")
        shutil.copy2(settings.path, backup)
    else:
        original = {}
    # Merge only the two OCR paths. Preserve all preferences, unknown keys and
    # the user's chosen languages and history/export directories.
    original.update(ocr_path=executable, ocr_data_dir=directory)
    atomic_bytes(settings.path, json.dumps(original, indent=2).encode("utf-8"))
    print(f"OCR runtime: {executable}")
    print(f"OCR language folder: {directory}")
    print(f"Offline OCR and opaque-image checks passed. Configured language: {languages}")


def check_native_capture():
    windows.require_windows()
    monitors = windows.monitor_rectangles()
    mappings = windows.map_displays(QApplication.screens(), monitors)
    mapped = {item.device.casefold() for item in mappings}
    if mapped != {name.casefold() for name, rect in monitors}:
        raise RuntimeError("Qt and Windows reported different active displays. Wait for the layout to settle, then rerun the updater.")
    for item in mappings:
        image = windows.grab_pixels(item.physical)
        if image.isNull() or image.size() != item.physical.size():
            raise RuntimeError(f"Capture buffer validation failed for {item.device}.")
        print(f"Display check passed: {item.screen.name()} -> {item.device}; "
              f"{image.width()} x {image.height()} physical pixels; scale {item.screen.devicePixelRatio():g}")
        del image
    print("Monitor mapping and native capture buffers passed. No screenshots were written to disk.")


def configure_autosave(directory):
    """Migrate once, preserving later folder choices and unrelated settings."""
    settings = Settings()
    original = json.loads(settings.path.read_text(encoding='utf-8')) if settings.path.exists() else {}
    if not isinstance(original, dict):
        raise ValueError('Settings must be a JSON object; the original file was left unchanged.')
    target = Path(original.get('screenshots_dir') or directory)
    target.mkdir(parents=True, exist_ok=True)
    probe = target / ('.beastsnip-write-check-' + uuid.uuid4().hex)
    try:
        atomic_bytes(probe, b'')
    finally:
        probe.unlink(missing_ok=True)
    if settings.path.exists():
        shutil.copy2(settings.path, settings.path.with_name('settings.major-backup-' + uuid.uuid4().hex + '.json'))
    original.setdefault('auto_save', True)
    original['screenshots_dir'] = str(target)
    atomic_bytes(settings.path, json.dumps(original, indent=2).encode('utf-8'))
    print('Screenshots folder is writable: ' + str(target))
    print('Automatic capture saving: ' + ('on' if original['auto_save'] else 'off (existing preference preserved)'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--locate-ocr", action="store_true")
    action.add_argument("--repair-ocr", action="store_true")
    action.add_argument("--check-native", action="store_true")
    action.add_argument("--configure-autosave", metavar="FOLDER")
    args = parser.parse_args()
    try:
        if args.locate_ocr:
            print(find_tesseract(Settings()["ocr_path"]))
            return 0
        windows.enable_dpi_awareness()
        app = QApplication.instance() or QApplication(["BeastSnip maintenance"])
        if args.configure_autosave:
            configure_autosave(args.configure_autosave)
        elif args.repair_ocr:
            repair_ocr()
        else:
            check_native_capture()
        return 0
    except RuntimeFailure as error:
        print(str(error), file=sys.stderr)
        return 3
    except Exception as error:
        print(f"BeastSnip maintenance failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
