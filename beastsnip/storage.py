"""Private, flattened history. SQLite is the authoritative image store."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from functools import wraps
import threading
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .config import atomic_bytes
from .document import encode_image


_WRITE_LOCK = threading.RLock()


def serialized(function):
    @wraps(function)
    def call(*args, **kwargs):
        with _WRITE_LOCK:
            return function(*args, **kwargs)
    return call


class History:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "history.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("""CREATE TABLE IF NOT EXISTS captures (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            ocr TEXT NOT NULL DEFAULT '', image BLOB NOT NULL, thumbnail BLOB NOT NULL)""")
        self.db.commit()

    @serialized
    def save(self, image, item_id=None, title=None, tags=None, ocr=""):
        image_bytes = encode_image(image)
        thumb = image.scaled(320, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        item_id = item_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        previous = self.db.execute("SELECT title,tags,created FROM captures WHERE id=?", (item_id,)).fetchone()
        title = title if title is not None else (previous["title"] if previous else datetime.now().strftime("Capture %Y-%m-%d %H-%M-%S"))
        tags = tags if tags is not None else (previous["tags"] if previous else "")
        created = previous["created"] if previous else now
        # Remove an old materialized file first. It is a convenience copy, never
        # the source of truth; failure aborts so an old unredacted copy isn't kept.
        materialized = self.directory / f"{item_id}.png"
        if materialized.exists():
            materialized.unlink()
        with self.db:
            self.db.execute("""INSERT OR REPLACE INTO captures
                (id,title,tags,created,width,height,ocr,image,thumbnail) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item_id, title, tags, created, image.width(), image.height(), ocr, image_bytes, encode_image(thumb)))
        return item_id

    def search(self, term=""):
        pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        return self.db.execute("""SELECT id,title,tags,created,width,height,thumbnail FROM captures
            WHERE title LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' OR ocr LIKE ? ESCAPE '\\'
            ORDER BY created DESC, rowid DESC""", (pattern, pattern, pattern)).fetchall()

    def image(self, item_id):
        row = self.db.execute("SELECT image FROM captures WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise FileNotFoundError("This history item no longer exists.")
        result = QImage.fromData(row["image"], "PNG")
        if result.isNull():
            raise OSError("This history image is damaged.")
        return result

    def rename(self, item_id, title, tags):
        with self.db:
            self.db.execute("UPDATE captures SET title=?,tags=? WHERE id=?", (title, tags, item_id))

    @serialized
    def materialize(self, item_id):
        path = self.directory / f"{item_id}.png"
        atomic_bytes(path, encode_image(self.image(item_id)))
        return path

    @serialized
    def delete(self, item_id):
        (self.directory / f"{item_id}.png").unlink(missing_ok=True)
        with self.db:
            self.db.execute("DELETE FROM captures WHERE id=?", (item_id,))

    @serialized
    def clear(self):
        for row in self.search():
            self.delete(row["id"])
        self.db.execute("VACUUM")

    def close(self):
        self.db.close()
