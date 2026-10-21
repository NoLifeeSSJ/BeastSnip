import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import shutil
import unittest

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from beastsnip.document import Annotation, Document
from beastsnip.ocr import OCRJob
from test_document import APP


@unittest.skipUnless(shutil.which("tesseract"), "Optional Tesseract runtime not installed")
class OCRIntegrationTests(unittest.TestCase):
    def image(self):
        image = QImage(1000, 200, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        font = QFont("Arial")
        font.setPixelSize(62)
        painter.setFont(font)
        painter.setPen(QColor("black"))
        painter.drawText(QRectF(35, 30, 940, 130), Qt.AlignmentFlag.AlignCenter, "BEASTSNIP LOCAL 12345")
        painter.end()
        return image

    def recognize(self, image):
        job = OCRJob(image, shutil.which("tesseract"), "eng")
        results = []
        job.signals.finished.connect(lambda text, error: results.append((text, error)))
        job.run()
        self.assertEqual(results[0][1], "")
        return results[0][0]

    def test_real_local_ocr_reads_rendered_pixels(self):
        text = self.recognize(self.image())
        self.assertIn("LOCAL", text.upper())
        self.assertIn("12345", text)

    def test_redacted_text_is_not_available_to_ocr(self):
        doc = Document(self.image())
        doc.add(Annotation("redact", [QPointF(0, 0), QPointF(1000, 200)]))
        self.assertEqual(self.recognize(doc.flatten()).strip(), "")


if __name__ == "__main__":
    unittest.main()
