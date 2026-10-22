import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PySide6.QtCore import QPointF, QRectF
from beastsnip.document import Annotation, Document, encode_image
from beastsnip.projects import RecoveryJournal, encode_project, load_project, project_snapshot, save_project
from test_autosave import ControlledWorker
from test_document import APP, white_image


class ProjectTests(unittest.TestCase):
    def test_large_repeated_ocr_history_is_trimmed_to_a_readable_project_and_oversized_current_text_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Document(white_image())
            for n in range(10):
                doc.ocr_text = str(n) + 'x' * 1_000_000
                doc.checkpoint()
            doc.ocr_text = 'Latest ' + 'x' * 1_000_000
            path = Path(directory) / 'large-text.beastsnip'
            save_project(path, project_snapshot(doc))
            restored, _ = load_project(path)
            self.assertEqual(restored.ocr_text, doc.ocr_text)
            self.assertGreater(len(restored.undo_stack), 0)
            self.assertLess(len(restored.undo_stack), 10)
            original = path.read_bytes()
            doc.ocr_text = 'x' * 2_000_001
            with self.assertRaises(ValueError):
                save_project(path, project_snapshot(doc))
            self.assertEqual(path.read_bytes(), original)

    def test_project_restores_editable_objects_text_undo_redo_and_opaque_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Document(white_image())
            doc.add(Annotation('text', [QPointF(30, 40)], text='Unicode: café\nSecond line', offset=QPointF(2, 3)))
            doc.add(Annotation('redact', [QPointF(10, 10), QPointF(90, 90)]))
            doc.ocr_text = 'Editable extracted text'
            path = Path(directory) / 'capture.beastsnip'
            save_project(path, project_snapshot(doc, r'C:\SnipsV1\Screenshots\capture.png'))
            restored, hint = load_project(path)
            self.assertEqual(len(restored.annotations), 2)
            self.assertEqual(restored.annotations[0].text, 'Unicode: café\nSecond line')
            self.assertEqual(restored.annotations[0].offset, QPointF(2, 3))
            self.assertEqual(restored.ocr_text, 'Editable extracted text')
            self.assertTrue(hint.endswith('capture.png'))
            self.assertFalse(restored.dirty)
            self.assertEqual(restored.base.pixelColor(20, 20).name(), '#ffffff')
            self.assertEqual(restored.flatten().pixelColor(20, 20).name(), '#000000')
            restored.undo()
            self.assertEqual(len(restored.annotations), 1)
            restored.redo()
            self.assertEqual(restored.flatten().pixelColor(20, 20).name(), '#000000')

    def test_crop_and_redo_history_survive_and_project_images_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Document(white_image())
            for n in range(4):
                doc.add(Annotation('number', [QPointF(30 + n * 20, 100)], number=n + 1))
            doc.crop(QRectF(0, 0, 120, 100))
            doc.undo()
            path = Path(directory) / 'state.beastsnip'
            save_project(path, project_snapshot(doc))
            with zipfile.ZipFile(path) as archive:
                self.assertLessEqual(len([n for n in archive.namelist() if n.endswith('.png')]), 2)
            restored, _ = load_project(path)
            self.assertEqual(len(restored.annotations), 4)
            restored.redo()
            self.assertEqual(restored.base.width(), 120)
            self.assertEqual(restored.annotations, [])

    def test_malicious_paths_unknown_schema_and_oversized_png_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.beastsnip'
            raw = encode_project(project_snapshot(Document(white_image())))
            for mutation in ('path', 'schema', 'image'):
                with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(path, 'w') as target:
                    for name in source.namelist():
                        data = source.read(name)
                        if name == 'project.json' and mutation == 'schema':
                            manifest = json.loads(data); manifest['schema'] = 999
                            data = json.dumps(manifest).encode()
                        if name.endswith('.png') and mutation == 'image':
                            data = data[:16] + (100000).to_bytes(4, 'big') * 2 + data[24:]
                        target.writestr(name, data)
                    if mutation == 'path':
                        target.writestr('../outside.txt', b'never extract me')
                with self.assertRaises(ValueError):
                    load_project(path)
                self.assertFalse((Path(directory).parent / 'outside.txt').exists())

    def test_recovery_serialises_latest_session_and_does_not_leak_into_export(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = ControlledWorker()
            journal = RecoveryJournal(Path(directory) / 'session.beastsnip', worker.submit)
            self.addCleanup(lambda: journal.timer.stop())
            first = Document(white_image())
            journal.attach(first); journal.flush()
            second = Document(white_image(300, 200))
            second.add(Annotation('redact', [QPointF(10, 10), QPointF(90, 90)]))
            journal.attach(second); journal.flush()
            self.assertEqual(len(worker.jobs), 1)
            worker.finish(); worker.finish()
            restored, _ = load_project(journal.path)
            self.assertEqual(restored.base.width(), 300)
            self.assertEqual(restored.flatten().pixelColor(20, 20).name(), '#000000')
            self.assertFalse(journal.pending)
            journal.clear()
            self.assertFalse(journal.path.exists())

    def test_disabled_recovery_never_writes_and_failed_save_is_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = ControlledWorker()
            blocked = Path(directory) / 'blocked'; blocked.write_text('keep')
            journal = RecoveryJournal(blocked / 'session.beastsnip', worker.submit, enabled=False)
            self.addCleanup(lambda: journal.timer.stop())
            journal.attach(Document(white_image())); journal.flush()
            self.assertEqual(worker.jobs, [])
            journal.enabled = True; journal.schedule(); journal.flush(); worker.finish()
            self.assertTrue(journal.error)
            self.assertTrue(journal.pending)
            journal.path = Path(directory) / 'recovered.beastsnip'
            journal.flush(); worker.finish()
            self.assertEqual(journal.error, '')
            self.assertTrue(journal.path.exists())
