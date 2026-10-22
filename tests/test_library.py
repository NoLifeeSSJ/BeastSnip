from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from PySide6.QtGui import QImage
from beastsnip.library import (LibraryIndex, date_matches, export_pngs, path_key,
    rename_png, restore_trashed, trash_pngs)
from test_document import APP, white_image


class LibraryTests(unittest.TestCase):
    def test_favourites_survive_reopen_and_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'capture.png'; white_image().save(str(path))
            index = LibraryIndex(root / 'library.sqlite3')
            index.set_favourite([path], True)
            self.assertIn(path_key(path), LibraryIndex(index.path).favourites())
            target = rename_png(path, 'A useful capture')
            index.move(path, target)
            self.assertIn(path_key(target), index.favourites())
            self.assertNotIn(path_key(path), index.favourites())

    def test_rename_rejects_windows_reserved_names_and_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.png'; white_image().save(str(path))
            existing = Path(directory) / 'existing.png'; existing.write_bytes(b'keep')
            for name in ('../escape', 'CON', 'AUX.txt', 'LPT1', 'bad:name', ''):
                with self.assertRaises(ValueError):
                    rename_png(path, name)
            with self.assertRaises(FileExistsError):
                rename_png(path, 'existing')
            self.assertEqual(existing.read_bytes(), b'keep')
            self.assertTrue(path.exists())

    def test_bulk_export_flattens_metadata_and_never_replaces_existing_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'exports'; target.mkdir()
            source = root / 'capture.png'
            image = white_image(); image.setText('secret', 'strip me'); image.save(str(source))
            (target / source.name).write_bytes(b'keep')
            results, errors = export_pngs([source, root / 'missing.png'], target)
            self.assertEqual(len(results), 1); self.assertEqual(len(errors), 1)
            self.assertEqual((target / source.name).read_bytes(), b'keep')
            self.assertEqual(QImage(results[0]).textKeys(), [])

    def test_bulk_delete_can_be_undone_without_overwriting_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f'capture-{n}.png' for n in range(3)]
            for path in paths: white_image().save(str(path))
            entries, errors = trash_pngs(paths, root)
            self.assertFalse(errors); self.assertEqual(len(entries), 3)
            self.assertFalse(any(path.exists() for path in paths))
            paths[0].write_bytes(b'new file')
            restored, errors = restore_trashed(entries)
            self.assertFalse(errors); self.assertEqual(len(restored), 3)
            self.assertEqual(paths[0].read_bytes(), b'new file')
            self.assertTrue((root / 'capture-0 (2).png').exists())

    def test_date_filters_use_local_calendar_days(self):
        now = datetime(2026, 10, 22, 12)
        timestamp = lambda days: (now - timedelta(days=days)).timestamp()
        self.assertTrue(date_matches(timestamp(0), 'today', now))
        self.assertFalse(date_matches(timestamp(1), 'today', now))
        self.assertTrue(date_matches(timestamp(6), 'week', now))
        self.assertFalse(date_matches(timestamp(7), 'week', now))
        self.assertTrue(date_matches(timestamp(29), 'month', now))
        self.assertFalse(date_matches(timestamp(30), 'month', now))
