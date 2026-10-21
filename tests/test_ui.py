import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from beastsnip.app import MainWindow
from beastsnip.document import Annotation, Document
from beastsnip.editor import Canvas
from beastsnip.ocr import OCRJob, find_tesseract
from beastsnip.windows import parse_hotkey
from test_document import APP, white_image


class UITests(unittest.TestCase):
    def test_crop_at_zoom_uses_image_coordinates(self):
        canvas = Canvas()
        canvas.resize(800, 600)
        doc = Document(white_image(800, 600))
        doc.add(Annotation("redact", [QPointF(210, 160), QPointF(260, 200)]))
        canvas.set_document(doc)
        canvas.show()
        APP.processEvents()
        canvas.actual_size()
        canvas.zoom(1.7)
        canvas.set_tool("crop")
        start = canvas.mapFromScene(QPointF(200, 150))
        end = canvas.mapFromScene(QPointF(400, 350))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertLessEqual(abs(doc.base.width() - 200), 2)
        self.assertLessEqual(abs(doc.base.height() - 200), 2)
        self.assertEqual(doc.flatten().pixelColor(20, 20).name(), "#000000")
        doc.undo()
        self.assertEqual(len(doc.annotations), 1)
        canvas.close()

    def test_ui_and_history_save_through_worker(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BEASTSNIP_DATA_DIR": directory}):
            window = MainWindow(smoke=True)
            window.set_document(white_image())
            window.doc.add(Annotation("redact", [QPointF(10, 10), QPointF(60, 60)]))
            window.save_history()
            for _ in range(200):
                APP.processEvents()
                if not window.history_busy:
                    break
                QTest.qWait(10)
            self.assertFalse(window.history_busy)
            self.assertEqual(len(window.history.search()), 1)
            self.assertFalse(window.doc.dirty)
            self.assertEqual(window.history.image(window.doc.history_id).pixelColor(20, 20).name(), "#000000")
            window.integration.close()
            window.tray.hide()
            window.quitting = True
            window.history.close()
            window.close()

    def test_missing_ocr_actionable_error(self):
        with patch("beastsnip.ocr.shutil.which", return_value=None), patch("beastsnip.ocr.Path.is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "winget install"):
                find_tesseract()

    def test_ocr_failure_emits_error_not_fabricated_text(self):
        job = OCRJob(white_image(), "/definitely/not/tesseract", "eng")
        results = []
        job.signals.finished.connect(lambda text, error: results.append((text, error)))
        job.run()
        self.assertEqual(results[0][0], "")
        self.assertTrue(results[0][1])

    def test_hotkey_validation(self):
        self.assertEqual(parse_hotkey("Ctrl+Alt+S"), (0x4003, ord("S")))
        self.assertEqual(parse_hotkey("Ctrl+Shift+F12"), (0x4006, 0x7B))
        for invalid in ("S", "Ctrl+???", "Ctrl+F25", "Super+S"):
            with self.assertRaises(ValueError):
                parse_hotkey(invalid)


if __name__ == "__main__":
    unittest.main()
