"""Favourites and reversible file operations for the PNG screenshot library."""
from contextlib import closing
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid

from PySide6.QtGui import QImage

from .config import atomic_bytes
from .document import save_image


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


class LibraryIndex:
    def __init__(self, database):
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS favourites (path TEXT PRIMARY KEY)')
            db.commit()

    def favourites(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {row[0] for row in db.execute('SELECT path FROM favourites')}

    def set_favourite(self, paths, enabled):
        with closing(sqlite3.connect(self.path)) as db:
            for path in paths:
                if enabled:
                    db.execute('INSERT OR IGNORE INTO favourites VALUES (?)', (path_key(path),))
                else:
                    db.execute('DELETE FROM favourites WHERE path=?', (path_key(path),))
            db.commit()

    def move(self, old, new):
        if path_key(old) == path_key(new):
            return
        if path_key(old) in self.favourites():
            self.set_favourite([new], True)
            self.set_favourite([old], False)


def date_matches(timestamp, period, now=None):
    now = now or datetime.now()
    date = datetime.fromtimestamp(timestamp).date()
    if period == 'today':
        return date == now.date()
    days = {'week': 7, 'month': 30}.get(period)
    return days is None or now.date() - timedelta(days=days - 1) <= date <= now.date()


def unique_destination(directory, name):
    directory = Path(directory)
    target, number = directory / name, 2
    while target.exists():
        target = directory / f'{Path(name).stem} ({number}){Path(name).suffix}'
        number += 1
    return target


def rename_png(path, name):
    path = Path(path)
    name = name.strip()
    if name.lower().endswith('.png'):
        name = name[:-4]
    if not name or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' ')) or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name):
        raise ValueError('Choose a valid Windows filename without folder separators.')
    target = path.with_name(name + '.png')
    if target != path and target.exists():
        raise FileExistsError('A screenshot already has this name. Choose another name.')
    if target != path:
        path.rename(target)
    return target


def export_pngs(paths, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    for source in map(Path, paths):
        try:
            image = QImage(str(source))
            if image.isNull():
                raise OSError('Image is missing or unreadable')
            target = unique_destination(directory, source.name)
            save_image(target, image)
            results.append(str(target))
        except Exception as error:
            errors.append(source.name + ': ' + str(error))
    return results, errors


def trash_pngs(paths, directory):
    directory = Path(directory).resolve()
    batch = directory / '.BeastSnipTrash' / uuid.uuid4().hex
    entries, errors = [], []
    for source in map(Path, paths):
        try:
            if source.resolve().parent != directory or source.suffix.lower() != '.png':
                raise ValueError('Only PNGs in the current Screenshots folder can be deleted here')
            batch.mkdir(parents=True, exist_ok=True)
            target = batch / source.name
            shutil.move(str(source), str(target))
            entries.append({'source': str(source), 'trashed': str(target)})
            atomic_bytes(batch / 'restore.json', json.dumps(entries).encode('utf-8'))
        except Exception as error:
            errors.append(source.name + ': ' + str(error))
    return entries, errors


def restore_trashed(entries):
    restored, errors = [], []
    for entry in entries:
        try:
            original = Path(entry['source'])
            target = unique_destination(original.parent, original.name)
            shutil.move(entry['trashed'], target)
            restored.append((entry['source'], str(target)))
        except Exception as error:
            errors.append(str(error))
    return restored, errors
