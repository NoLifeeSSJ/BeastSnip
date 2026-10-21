import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from beastsnip.document import Annotation, Document
from beastsnip.storage import History
from test_document import white_image


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.history = History(self.temporary.name)

    def tearDown(self):
        self.history.close()
        self.temporary.cleanup()

    def test_persistence_search_and_rename(self):
        item = self.history.save(white_image(), title="Helpdesk VPN", tags="network, guide", ocr="EXPLICIT OCR")
        self.history.close()
        self.history = History(self.temporary.name)
        self.assertEqual(self.history.search("vpn")[0]["id"], item)
        self.assertEqual(len(self.history.search("network")), 1)
        self.assertEqual(len(self.history.search("EXPLICIT OCR")), 1)
        self.assertEqual(len(self.history.search("%")), 0)
        self.assertEqual(self.history.image(item).width(), 240)
        self.history.rename(item, "New title", "device")
        self.assertEqual(len(self.history.search("VPN")), 0)
        self.assertEqual(len(self.history.search("device")), 1)

    def test_update_replaces_pixels_thumbnail_and_ocr(self):
        doc = Document(white_image())
        item = self.history.save(doc.flatten(), ocr="unredacted text")
        old_file = self.history.materialize(item)
        self.assertTrue(old_file.exists())
        old_thumbnail = bytes(self.history.search()[0]["thumbnail"])
        doc.add(Annotation("redact", [QPointF(0, 0), QPointF(120, 100)]))
        result = self.history.save(doc.flatten(), item_id=item, ocr=doc.ocr_text)
        self.assertEqual(result, item)
        self.assertEqual(len(self.history.search()), 1)
        self.assertEqual(len(self.history.search("unredacted")), 0)
        self.assertFalse(old_file.exists())
        self.assertEqual(self.history.image(item).pixelColor(50, 50), QColor("black"))
        self.assertNotEqual(bytes(self.history.search()[0]["thumbnail"]), old_thumbnail)

    def test_missing_materialized_file_does_not_break_gallery(self):
        item = self.history.save(white_image())
        path = self.history.materialize(item)
        path.unlink()
        self.assertFalse(self.history.image(item).isNull())
        self.assertTrue(self.history.materialize(item).exists())

    def test_delete_preserves_separate_export(self):
        item = self.history.save(white_image())
        history_file = self.history.materialize(item)
        separate = Path(self.temporary.name) / "separate-export.png"
        separate.write_bytes(history_file.read_bytes())
        self.history.delete(item)
        self.assertFalse(history_file.exists())
        self.assertTrue(separate.exists())
        with self.assertRaises(FileNotFoundError):
            self.history.image(item)

    def test_clear_history(self):
        for _ in range(3):
            self.history.save(white_image())
        self.history.clear()
        self.assertEqual(self.history.search(), [])

    def test_concurrent_materialization_cannot_leave_an_old_unredacted_copy(self):
        from beastsnip.config import atomic_bytes
        item = self.history.save(white_image())
        entered, release, saved = threading.Event(), threading.Event(), threading.Event()
        failures = []
        directory = self.temporary.name
        def delayed_write(path, data):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release the materialization worker")
            atomic_bytes(path, data)
        def materialize():
            history = History(directory)
            try:
                history.materialize(item)
            except Exception as error:
                failures.append(error)
            finally:
                history.close()
        def update():
            history = History(directory)
            try:
                image = white_image()
                image.fill(QColor("black"))
                history.save(image, item_id=item)
                saved.set()
            except Exception as error:
                failures.append(error)
            finally:
                history.close()
        with patch("beastsnip.storage.atomic_bytes", side_effect=delayed_write):
            first = threading.Thread(target=materialize)
            first.start()
            self.assertTrue(entered.wait(5))
            second = threading.Thread(target=update)
            second.start()
            try:
                self.assertFalse(saved.wait(.1))
            finally:
                release.set()
                first.join(5)
                second.join(5)
        self.assertFalse(failures)
        self.assertTrue(saved.is_set())
        self.assertFalse((Path(directory) / f"{item}.png").exists())
        self.assertEqual(self.history.image(item).pixelColor(20, 20), QColor("black"))


if __name__ == "__main__":
    unittest.main()
