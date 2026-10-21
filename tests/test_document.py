import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from beastsnip.document import Annotation, Document, encode_image, save_image

APP = QApplication.instance() or QApplication([])


def white_image(width=240, height=180):
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    return image


class DocumentTests(unittest.TestCase):
    def test_redaction_is_opaque_and_flattened_png_has_no_source_metadata(self):
        image = white_image()
        image.setText("secret", "do not export")
        doc = Document(image)
        doc.add(Annotation("redact", [QPointF(30, 20), QPointF(110, 80)], color="#ffffff"))
        exported = QImage.fromData(encode_image(doc.flatten()))
        for y in range(20, 80):
            for x in range(30, 110):
                self.assertEqual(exported.pixelColor(x, y), QColor("black"))
        self.assertEqual(exported.textKeys(), [])
        self.assertEqual(exported.pixelColor(10, 10), QColor("white"))
        self.assertEqual(doc.base.pixelColor(50, 50), QColor("white"))

    def test_crop_undo_redo_restores_image_and_editable_objects(self):
        doc = Document(white_image())
        doc.add(Annotation("redact", [QPointF(30, 20), QPointF(110, 80)]))
        doc.crop(QRectF(20, 10, 100, 80))
        self.assertEqual((doc.base.width(), doc.base.height()), (100, 80))
        self.assertEqual(len(doc.annotations), 0)
        self.assertEqual(doc.base.pixelColor(10, 10), QColor("black"))
        doc.undo()
        self.assertEqual(doc.base.width(), 240)
        self.assertEqual(len(doc.annotations), 1)
        doc.redo()
        self.assertEqual(doc.base.width(), 100)
        self.assertEqual(len(doc.annotations), 0)

    def test_crop_outside_bounds_and_reject_empty(self):
        doc = Document(white_image())
        doc.crop(QRectF(-10, -10, 50, 50))
        self.assertEqual((doc.base.width(), doc.base.height()), (40, 40))
        with self.assertRaises(ValueError):
            doc.crop(QRectF(500, 500, 10, 10))

    def test_move_delete_and_undo_branch_dirty_state(self):
        doc = Document(white_image())
        item = Annotation("filled", [QPointF(10, 10), QPointF(20, 20)], color="#ff0000")
        doc.add(item)
        doc.mark_saved()
        item.offset = QPointF(30, 40)
        doc.replace(0, item)
        self.assertEqual(doc.flatten().pixelColor(45, 55), QColor("#ff0000"))
        self.assertTrue(doc.dirty)
        doc.undo()
        self.assertFalse(doc.dirty)
        doc.remove(0)
        self.assertTrue(doc.dirty)
        self.assertFalse(doc.redo_stack)
        doc.undo()
        self.assertEqual(len(doc.annotations), 1)

    def test_all_annotation_tools_render(self):
        for kind in ("pen", "highlight", "arrow", "rect", "filled", "ellipse", "text", "number", "redact"):
            with self.subTest(kind=kind):
                doc = Document(white_image())
                doc.add(Annotation(kind, [QPointF(60, 60), QPointF(120, 120)], text="Test", color="#a020f0"))
                rendered = doc.flatten()
                self.assertNotEqual(encode_image(rendered), encode_image(white_image()))

    def test_ocr_text_invalidated_on_edit_and_restored_on_undo(self):
        doc = Document(white_image())
        doc.ocr_text = "private extracted text"
        doc.add(Annotation("redact", [QPointF(0, 0), QPointF(100, 100)]))
        self.assertEqual(doc.ocr_text, "")
        doc.undo()
        self.assertEqual(doc.ocr_text, "private extracted text")

    def test_jpeg_background_and_atomic_output(self):
        image = QImage(40, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "capture.jpg"
            save_image(path, image, 95)
            result = QImage(str(path))
            self.assertFalse(result.isNull())
            self.assertGreater(result.pixelColor(20, 20).red(), 245)
            self.assertFalse(result.hasAlphaChannel())

    def test_reverse_direction_redaction(self):
        doc = Document(white_image())
        doc.add(Annotation("redact", [QPointF(90, 80), QPointF(10, 20)]))
        self.assertEqual(doc.flatten().pixelColor(15, 25), QColor("black"))


if __name__ == "__main__":
    unittest.main()
