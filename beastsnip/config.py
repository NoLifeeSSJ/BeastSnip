import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import QSaveFile, QIODevice


def data_dir():
    root = os.environ.get("BEASTSNIP_DATA_DIR")
    if root:
        return Path(root)
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "BeastSnip"


def resource(name):
    return Path(__file__).resolve().parent / "resources" / name


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = QSaveFile(str(path))
    output.setDirectWriteFallback(False)
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(data) != len(data) or not output.commit():
        raise OSError(output.errorString())


class Settings:
    defaults = {
        "delay": 0, "hotkey": "Ctrl+Alt+S", "auto_copy": False,
        "quick_capture": False, "recover_session": True, "magnifier": True,
        "auto_history": False, "auto_save": True, "screenshots_dir": r"C:\SnipsV1\Screenshots" if os.name == "nt" and not os.environ.get("BEASTSNIP_DATA_DIR") else "", "close_to_tray": True, "close_explained": False,
        "save_dir": str(Path.home() / "Pictures" / "BeastSnip"),
        "history_dir": "", "jpeg_quality": 92, "ocr_path": "", "ocr_language": "eng", "ocr_data_dir": "",
    }

    def __init__(self):
        self.path = data_dir() / "settings.json"
        self.values = self.defaults.copy()
        self.values["history_dir"] = str(data_dir() / "history")
        if not self.values["screenshots_dir"]:
            self.values["screenshots_dir"] = str(data_dir() / "Screenshots")
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Settings must be an object")
            for key, default in self.defaults.items():
                value = loaded.get(key)
                if type(value) is type(default):
                    self.values[key] = value
            if self.values["delay"] not in (0, 3, 5, 10):
                self.values["delay"] = 0
            self.values["jpeg_quality"] = max(1, min(100, self.values["jpeg_quality"]))
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logging.warning("Could not load settings; using defaults")

    def __getitem__(self, key):
        return self.values[key]

    def save(self):
        atomic_bytes(self.path, json.dumps(self.values, indent=2).encode("utf-8"))
