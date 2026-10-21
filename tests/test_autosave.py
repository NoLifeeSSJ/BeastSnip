import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF
from PySide6.QtTest import QSignalSpy
from PySide6.QtGui import QImage

from beastsnip.autosave import AutosaveSession, capture_path
from beastsnip.document import Annotation, Document
from beastsnip.maintenance import configure_autosave
from beastsnip.config import Settings
from test_document import APP, white_image


class ControlledWorker:
    def __init__(self):
        self.jobs = []

    def submit(self, function, callback):
        self.jobs.append((function, callback))

    def finish(self):
        function, callback = self.jobs.pop(0)
        try:
            result, error = function(), ''
        except Exception as exc:
            result, error = None, str(exc)
        callback(result, error)


class AutosaveTests(unittest.TestCase):
    def session(self, directory):
        doc = Document(white_image())
        doc.saved_revision = -1
        worker = ControlledWorker()
        session = AutosaveSession(doc, capture_path(directory), worker.submit)
        self.addCleanup(lambda: session.timer.stop())
        return doc, worker, session

    def test_capture_names_are_unique_and_initial_png_is_flattened(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len({capture_path(directory) for _ in range(100)}), 100)
            doc, worker, session = self.session(directory)
            doc.base.setText('secret', 'metadata must not be exported')
            session.flush()
            self.assertTrue(session.busy)
            worker.finish()
            saved = QImage(str(session.path))
            self.assertFalse(saved.isNull())
            self.assertEqual(saved.textKeys(), [])
            self.assertFalse(doc.dirty)

    def test_edits_while_initial_write_is_busy_are_serialised_and_latest_redaction_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, worker, session = self.session(directory)
            session.flush()
            for offset in range(4):
                doc.add(Annotation('redact', [QPointF(10 + offset, 10), QPointF(90, 90)]))
            session.flush()
            self.assertEqual(len(worker.jobs), 1)
            worker.finish()
            self.assertTrue(doc.dirty)
            self.assertEqual(len(worker.jobs), 1)
            worker.finish()
            self.assertEqual(QImage(str(session.path)).pixelColor(30, 30).name(), '#000000')
            self.assertEqual(len(list(Path(directory).glob('*.png'))), 1)
            self.assertFalse(doc.dirty)

    def test_failed_write_stays_pending_and_retry_can_use_a_writable_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked = Path(directory) / 'not-a-folder'
            blocked.write_text('keep me')
            doc, worker, session = self.session(blocked)
            session.flush()
            worker.finish()
            self.assertTrue(session.error)
            self.assertTrue(session.pending)
            self.assertTrue(doc.dirty)
            self.assertEqual(blocked.read_text(), 'keep me')
            session.path = capture_path(Path(directory) / 'recovered')
            session.flush()
            worker.finish()
            self.assertEqual(session.error, '')
            self.assertTrue(session.path.exists())
            self.assertFalse(doc.dirty)

    def test_save_completion_does_not_rebuild_the_canvas_or_erase_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, worker, session = self.session(directory)
            doc.ocr_text = 'Extracted text that has not been saved to history'
            changes = QSignalSpy(doc.changed)
            session.flush()
            worker.finish()
            self.assertEqual(changes.count(), 0)
            self.assertEqual(doc.saved_revision, doc.revision)
            self.assertTrue(doc.dirty)  # PNG does not store the OCR text.
            self.assertEqual(doc.ocr_text, 'Extracted text that has not been saved to history')

    def test_undo_and_redo_update_the_same_png(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, worker, session = self.session(directory)
            doc.add(Annotation('redact', [QPointF(10, 10), QPointF(90, 90)]))
            for action, colour in [(lambda: None, '#000000'), (doc.undo, '#ffffff'), (doc.redo, '#000000')]:
                action()
                session.flush()
                worker.finish()
                self.assertEqual(QImage(str(session.path)).pixelColor(30, 30).name(), colour)
            self.assertEqual(len(list(Path(directory).glob('*.png'))), 1)

    def test_retiring_flushes_the_last_edit_without_touching_the_next_document(self):
        with tempfile.TemporaryDirectory() as directory:
            doc, worker, session = self.session(directory)
            session.flush()
            worker.finish()
            doc.add(Annotation('redact', [QPointF(10, 10), QPointF(90, 90)]))
            next_doc = Document(white_image())
            next_doc.saved_revision = -1
            session.retire()
            worker.finish()
            self.assertFalse(doc.dirty)
            self.assertTrue(next_doc.dirty)
            self.assertEqual(QImage(str(session.path)).pixelColor(30, 30).name(), '#000000')
            self.assertFalse(session.timer.isActive())


class AutosaveMigrationTests(unittest.TestCase):
    def test_migration_preserves_legacy_preferences_and_later_custom_choices(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BEASTSNIP_DATA_DIR': directory}):
            path = Path(directory) / 'settings.json'
            legacy = {'auto_copy': True, 'ocr_path': 'working-tesseract.exe', 'ocr_language': 'eng+deu',
                      'history_dir': str(Path(directory) / 'existing history'), 'future_key': {'keep': True}}
            path.write_text(json.dumps(legacy))
            target = Path(directory) / "Snips O'Connor" / 'Screenshots'
            configure_autosave(target)
            migrated = json.loads(path.read_text())
            self.assertEqual({key: migrated[key] for key in legacy}, legacy)
            self.assertTrue(migrated['auto_save'])
            self.assertEqual(migrated['screenshots_dir'], str(target))
            self.assertTrue(target.is_dir())
            self.assertFalse(list(target.iterdir()))
            custom = Path(directory) / 'custom capture folder'
            migrated.update(auto_save=False, screenshots_dir=str(custom))
            path.write_text(json.dumps(migrated))
            configure_autosave(target)
            self.assertFalse(Settings()['auto_save'])
            self.assertEqual(Settings()['screenshots_dir'], str(custom))
            self.assertEqual(len(list(Path(directory).glob('settings.major-backup-*.json'))), 2)

    def test_unwritable_target_leaves_original_configuration_untouched(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BEASTSNIP_DATA_DIR': directory}):
            path = Path(directory) / 'settings.json'
            original = b'{"auto_copy": true, "ocr_path": "keep.exe"}'
            path.write_bytes(original)
            blocked = Path(directory) / 'file'
            blocked.write_text('not a directory')
            with self.assertRaises(OSError):
                configure_autosave(blocked / 'Screenshots')
            self.assertEqual(path.read_bytes(), original)
