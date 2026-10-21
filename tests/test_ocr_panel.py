import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import unittest

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QTextEdit

from beastsnip.document import Annotation, Document
from beastsnip.editor import Editor
from beastsnip.ocr_panel import OCRTextDialog
from beastsnip.style import STYLE
from test_document import APP, white_image


LONG_TEXT = "\n".join(f"Step {number}: Open the settings and choose the appropriate network connection." for number in range(1, 81))


class OCRPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_style = APP.styleSheet()
        APP.setStyleSheet(STYLE)

    @classmethod
    def tearDownClass(cls):
        APP.setStyleSheet(cls.old_style)

    def editor(self, width=1280, height=760):
        editor = Editor()
        editor.resize(width, height)
        editor.set_document(Document(white_image(1000, 700)))
        editor.show()
        APP.processEvents()
        self.addCleanup(editor.close)
        return editor

    def test_long_ocr_has_a_full_height_readable_sidebar(self):
        editor = self.editor()
        editor.show_ocr(LONG_TEXT)
        APP.processEvents()
        self.assertGreaterEqual(editor.ocr_text.viewport().height(), 400)
        self.assertGreaterEqual(editor.ocr_text.viewport().width(), 280)
        self.assertGreater(editor.ocr_panel.x(), editor.canvas.x())
        self.assertLessEqual(abs(editor.ocr_panel.height() - editor.canvas.height()), 2)
        self.assertEqual(editor.ocr_text.document().defaultFont().pointSize(), 12)
        self.assertGreater(editor.ocr_text.verticalScrollBar().maximum(), 0)
        self.assertEqual(editor.ocr_text.toPlainText(), LONG_TEXT)

    def test_laptop_window_keeps_text_readable_and_long_paths_wrap(self):
        editor = self.editor(900, 600)
        editor.show_ocr("C:/" + "long-path-segment/" * 60)
        APP.processEvents()
        self.assertGreaterEqual(editor.ocr_text.viewport().height(), 220)
        self.assertGreaterEqual(editor.ocr_panel.width(), 340)
        self.assertEqual(editor.ocr_text.horizontalScrollBar().maximum(), 0)
        self.assertTrue(editor.ocr_panel.copy_button.isVisible())
        self.assertTrue(editor.ocr_panel.expand_button.isVisible())

    def test_user_width_survives_reextraction_and_reopening(self):
        editor = self.editor()
        editor.show_ocr(LONG_TEXT)
        editor.splitter.setSizes([650, 500])
        APP.processEvents()
        width = editor.ocr_panel.width()
        editor.show_ocr("Another extraction")
        APP.processEvents()
        self.assertLessEqual(abs(editor.ocr_panel.width() - width), 2)
        editor.hide_ocr()
        APP.processEvents()
        self.assertGreaterEqual(editor.canvas.width(), editor.splitter.width() - 2)
        editor.show_ocr("Another extraction")
        APP.processEvents()
        self.assertLessEqual(abs(editor.ocr_panel.width() - width), 2)

    def test_text_shortcuts_copy_edit_and_undo_without_image_actions(self):
        editor = self.editor()
        doc = editor.canvas.doc
        doc.add(Annotation("number", [QPointF(50, 50)]))
        revision = doc.revision
        editor.show_ocr("Alpha Beta")
        APP.processEvents()
        image_copies = QSignalSpy(editor.copy_requested)
        editor.ocr_text.selectAll()
        QTest.keyClick(editor.ocr_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(APP.clipboard().text(), "Alpha Beta")
        self.assertEqual(image_copies.count(), 0)
        QTest.keyClicks(editor.ocr_text, "Changed")
        self.assertEqual(doc.ocr_text, "Changed")
        QTest.keyClick(editor.ocr_text, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.ocr_text.toPlainText(), "Alpha Beta")
        self.assertEqual(doc.revision, revision)
        self.assertEqual(len(doc.annotations), 1)

    def test_expanded_view_shares_edits_font_wrap_and_clipboard(self):
        editor = self.editor()
        editor.show_ocr("Recognized text")
        dialog = OCRTextDialog(editor.ocr_panel)
        self.addCleanup(dialog.close)
        dialog.show()
        APP.processEvents()
        self.assertGreaterEqual(dialog.text_edit.viewport().height(), min(400, dialog.screen().availableGeometry().height() - 300))
        dialog.text_edit.moveCursor(QTextCursor.MoveOperation.End)
        dialog.text_edit.insertPlainText(" with edits")
        self.assertEqual(editor.canvas.doc.ocr_text, "Recognized text with edits")
        QTest.keyClick(dialog.text_edit, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.ocr_text.toPlainText(), "Recognized text")
        QTest.keyClick(dialog.text_edit, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.ocr_text.toPlainText(), "Recognized text with edits")
        dialog.view.font_size.setValue(18)
        self.assertEqual(editor.ocr_panel.view.font_size.value(), 18)
        self.assertEqual(editor.ocr_text.document().defaultFont().pointSize(), 18)
        dialog.view.wrap.setChecked(False)
        self.assertEqual(editor.ocr_text.lineWrapMode(), QTextEdit.LineWrapMode.NoWrap)
        dialog.text_edit.selectAll()
        QTest.keyClick(dialog.text_edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(APP.clipboard().text(), "Recognized text with edits")
        dialog.accept()
        self.assertEqual(editor.ocr_text.toPlainText(), "Recognized text with edits")

    def test_each_view_wraps_to_its_own_width_after_expanding_and_returning(self):
        editor = self.editor()
        editor.show_ocr(LONG_TEXT)
        dialog = OCRTextDialog(editor.ocr_panel)
        self.addCleanup(dialog.close)
        dialog.show()
        APP.processEvents()
        self.assertGreater(dialog.text_edit.viewport().width(), editor.ocr_text.viewport().width())
        for text_edit in (editor.ocr_text, dialog.text_edit):
            self.assertEqual(text_edit.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(text_edit.document().size().width(), text_edit.viewport().width() + 1)
        dialog.text_edit.insertPlainText("Updated: ")
        dialog.accept()
        APP.processEvents()
        self.assertEqual(editor.ocr_text.horizontalScrollBar().maximum(), 0)
        self.assertLessEqual(editor.ocr_text.document().size().width(), editor.ocr_text.viewport().width() + 1)
        self.assertTrue(editor.canvas.doc.ocr_text.startswith("Updated: "))

    def test_expand_button_opens_a_modal_reader_and_keeps_edits(self):
        editor = self.editor()
        editor.show_ocr("Initial text")
        observed = []
        def read_and_close():
            dialog = APP.activeModalWidget()
            observed.append(isinstance(dialog, OCRTextDialog))
            if isinstance(dialog, OCRTextDialog):
                dialog.text_edit.setPlainText("Edited in expanded view")
            if dialog:
                dialog.accept()
        QTimer.singleShot(30, read_and_close)
        editor.ocr_panel.expand()
        self.assertEqual(observed, [True])
        self.assertEqual(editor.canvas.doc.ocr_text, "Edited in expanded view")

    def test_redaction_invalidates_both_views_and_new_image_clears_the_panel(self):
        editor = self.editor()
        editor.show_ocr("Sensitive extracted text")
        dialog = OCRTextDialog(editor.ocr_panel)
        self.addCleanup(dialog.close)
        editor.canvas.doc.add(Annotation("redact", [QPointF(0, 0), QPointF(100, 100)]))
        self.assertEqual(editor.canvas.doc.ocr_text, "")
        self.assertEqual(dialog.text_edit.toPlainText(), "")
        dialog.view.copy_text()
        self.assertEqual(APP.clipboard().text(), "")
        editor.show_ocr("Second image text")
        editor.set_document(Document(white_image()))
        self.assertTrue(editor.ocr_panel.isHidden())
        self.assertEqual(editor.ocr_text.toPlainText(), "")


if __name__ == "__main__":
    unittest.main()
