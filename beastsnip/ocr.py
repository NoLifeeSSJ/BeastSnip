"""Tesseract runs locally in a worker; screenshots travel through stdin only."""
import os
from pathlib import Path
import re
import shutil
import subprocess

from PySide6.QtCore import QObject, QRunnable, Signal

from .config import data_dir
from .document import encode_image


def registry_tesseract_paths():
    """Read installer metadata only, including custom/per-user install paths."""
    if os.name != "nt":
        return []
    import winreg
    paths = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\tesseract.exe", 0, winreg.KEY_READ | view) as key:
                    paths.append(winreg.QueryValueEx(key, "")[0])
            except OSError:
                pass
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0, winreg.KEY_READ | view) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, index)) as key:
                                name = str(winreg.QueryValueEx(key, "DisplayName")[0])
                                if "tesseract" not in name.lower():
                                    continue
                                try:
                                    location = str(winreg.QueryValueEx(key, "InstallLocation")[0]).strip('"')
                                    if location:
                                        paths.append(str(Path(location) / "tesseract.exe"))
                                except OSError:
                                    pass
                                try:
                                    icon = str(winreg.QueryValueEx(key, "DisplayIcon")[0])
                                    match = re.match(r'^"([^"]+)"', icon)
                                    paths.append(match.group(1) if match else re.sub(r",\s*-?\d+$", "", icon))
                                except OSError:
                                    pass
                        except OSError:
                            pass
            except OSError:
                pass
    return paths


def tesseract_candidates(configured=""):
    candidates = [configured, shutil.which("tesseract")]
    for key in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(key):
            root = Path(os.environ[key])
            candidates += [str(root / "Tesseract-OCR" / "tesseract.exe"),
                           str(root / "Programs" / "Tesseract-OCR" / "tesseract.exe")]
    for candidate in candidates:
        if candidate:
            path = Path(os.path.expandvars(str(candidate).strip().strip('"')))
            if path.is_file():
                yield str(path)
    for candidate in registry_tesseract_paths():
        path = Path(os.path.expandvars(str(candidate).strip().strip('"')))
        if path.name.casefold() == "tesseract.exe" and path.is_file():
            yield str(path)


def find_tesseract(configured=""):
    for candidate in tesseract_candidates(configured):
        return candidate
    raise RuntimeError("Offline OCR could not find Tesseract. Run Repair-OCR.ps1 in your BeastSnip folder, "
                       "or install with: winget install --id UB-Mannheim.TesseractOCR --exact\n"
                       "Then select tesseract.exe in Settings. Capture and editing work without it.")


def language_codes(language):
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", language):
        raise ValueError("OCR language must be a Tesseract language code, for example eng or eng+deu.")
    return list(dict.fromkeys(language.split("+")))


def tessdata_candidates(executable, configured=""):
    paths = [configured, str(data_dir() / "ocr" / "tessdata")]
    prefix = os.environ.get("TESSDATA_PREFIX")
    if prefix:
        paths.extend([prefix, str(Path(prefix) / "tessdata")])
    root = Path(executable).parent
    paths.extend([str(root / "tessdata"), str(root.parent / "share" / "tessdata"),
                  "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata",
                  "/usr/share/tessdata", "/usr/local/share/tessdata"])
    return [Path(os.path.expandvars(str(path).strip('"'))) for path in paths if path]


def find_tessdata(executable, language, configured=""):
    codes = language_codes(language)
    for directory in tessdata_candidates(executable, configured):
        if all((directory / f"{code}.traineddata").is_file() for code in codes):
            return str(directory)
    if configured:
        raise RuntimeError(f"OCR language files for {language} are missing from {configured}. Run Repair-OCR.ps1 or choose the correct OCR language folder in Settings.")
    return ""  # Tesseract may have another compiled-in location; --list-langs checks it.


def process_options():
    return {"creationflags": 0x08000000 if os.name == "nt" else 0, "timeout": 90}


def recognize(image, executable, language, configured_data=""):
    codes = language_codes(language)
    directory = find_tessdata(executable, language, configured_data)
    args = [executable]
    if directory:
        args += ["--tessdata-dir", directory]
    listing = subprocess.run(args + ["--list-langs"], capture_output=True, **process_options())
    available = set(line.strip() for line in listing.stdout.decode("utf-8", errors="replace").splitlines()[1:])
    missing = [code for code in codes if code not in available]
    if listing.returncode or missing:
        raise RuntimeError("Tesseract is installed, but the required language files are unavailable: "
                           + ", ".join(missing or codes) + ". Run Repair-OCR.ps1 in your BeastSnip folder.")
    result = subprocess.run(args + ["stdin", "stdout", "-l", language],
                            input=encode_image(image), capture_output=True, **process_options())
    if result.returncode:
        # Never show OCR stderr: a third-party log could contain screenshot text.
        raise RuntimeError("Tesseract could not process the image. Run Repair-OCR.ps1 to check its runtime and language files, then retry.")
    return result.stdout.decode("utf-8", errors="replace").strip()


class OCRSignals(QObject):
    finished = Signal(str, str)


class OCRJob(QRunnable):
    def __init__(self, image, executable, language, tessdata_dir=""):
        super().__init__()
        self.signals = OCRSignals()
        self.image, self.executable, self.language = image, executable, language
        self.tessdata_dir = tessdata_dir

    def run(self):
        try:
            text = recognize(self.image, self.executable, self.language, self.tessdata_dir)
            self.signals.finished.emit(text, "")
        except subprocess.TimeoutExpired:
            self.signals.finished.emit("", "OCR exceeded 90 seconds. Try a smaller selected area or run Repair-OCR.ps1.")
        except Exception as error:
            self.signals.finished.emit("", str(error))
