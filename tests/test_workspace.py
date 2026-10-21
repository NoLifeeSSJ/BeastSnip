import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from beastsnip.app import MainWindow
from beastsnip.document import Annotation
from beastsnip.dialogs import SettingsDialog
from beastsnip.editor import TOOLS
from beastsnip.style import STYLE
from beastsnip.ui import CommandPalette
from test_document import APP, white_image


def settle(window, timeout=3000):
    for _ in range(timeout // 10):
        APP.processEvents()
        if not window.tasks and not any(s.busy or (s.pending and not s.error) for s in window.autosaves):
            return
        QTest.qWait(10)
    raise AssertionError('Background operations did not finish')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {'BEASTSNIP_DATA_DIR': self.directory.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        old_style = APP.styleSheet()
        APP.setStyleSheet(STYLE)
        self.addCleanup(APP.setStyleSheet, old_style)
        self.window = MainWindow(smoke=True)
        self.window.settings.values['screenshots_dir'] = str(Path(self.directory.name) / 'Screenshots')
        self.addCleanup(self.close_window)

    def close_window(self):
        settle(self.window)
        self.window.shutdown()

    def test_capture_and_debounced_redaction_are_saved_without_extra_files(self):
        w = self.window
        w.captured(white_image())
        settle(w)
        path = w.autosave.path
        self.assertTrue(path.exists())
        self.assertFalse(w.doc.dirty)
        w.doc.add(Annotation('redact', [QPointF(10, 10), QPointF(80, 80)]))
        settle(w)
        self.assertEqual(QImage(str(path)).pixelColor(30, 30).name(), '#000000')
        self.assertEqual(len(list(path.parent.glob('*.png'))), 1)
        self.assertIn('Saved', w.editor.save_status.text())
        self.assertFalse(w.save_warning.isVisible())

    def test_autosave_failure_is_visible_and_can_be_retried(self):
        w = self.window
        blocked = Path(self.directory.name) / 'blocked'
        blocked.write_text('keep')
        w.settings.values['screenshots_dir'] = str(blocked / 'Screenshots')
        w.show()
        w.captured(white_image())
        settle(w)
        self.assertTrue(w.save_warning.isVisible())
        self.assertTrue(w.doc.dirty)
        self.assertEqual(w.editor.save_status.text(), 'Save failed · Retry with Save')
        w.settings.values['screenshots_dir'] = str(Path(self.directory.name) / 'recovered')
        w.retry_autosaves()
        settle(w)
        self.assertTrue(w.autosave.path.exists())
        self.assertFalse(w.doc.dirty)
        self.assertFalse(w.save_warning.isVisible())

    def test_imports_stay_untouched_until_save_and_disabling_autosave_is_respected(self):
        w = self.window
        source = Path(self.directory.name) / 'source.png'
        white_image().save(str(source))
        original = source.read_bytes()
        w.open_image(source)
        self.assertIsNone(w.autosave)
        w.doc.add(Annotation('redact', [QPointF(10, 10), QPointF(80, 80)]))
        w.quick_save()
        settle(w)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(QImage(str(w.autosave.path)).pixelColor(30, 30).name(), '#000000')
        w.settings.values['auto_save'] = False
        w.captured(white_image())
        settle(w)
        self.assertIsNone(w.autosave)
        self.assertTrue(w.doc.dirty)

    def test_reopening_a_saved_capture_updates_its_file_and_paste_creates_a_new_capture(self):
        w = self.window
        w.captured(white_image())
        settle(w)
        path = w.autosave.path
        w.show_gallery()
        settle(w)
        self.assertEqual(w.screenshots.count(), 1)
        w.screenshots.setCurrentRow(0)
        w.open_screenshot()
        settle(w)
        self.assertEqual(w.autosave.path, path)
        w.doc.add(Annotation('redact', [QPointF(10, 10), QPointF(80, 80)]))
        settle(w)
        self.assertEqual(QImage(str(path)).pixelColor(30, 30).name(), '#000000')
        APP.clipboard().setImage(white_image(120, 90))
        w.paste_image()
        settle(w)
        self.assertNotEqual(w.autosave.path, path)
        self.assertEqual(len(list(path.parent.glob('*.png'))), 2)
        w.show_gallery()
        settle(w)
        w.search.setText(path.stem)
        settle(w)
        self.assertEqual(w.screenshots.count(), 1)

    def test_tools_shortcuts_context_focus_and_existing_actions_remain_available(self):
        w = self.window
        w.resize(1000, 720)
        w.set_document(white_image())
        w.show()
        APP.processEvents()
        editor = w.editor
        for tool, label, key, hint in TOOLS:
            editor.canvas.setFocus()
            QTest.keyClick(editor.canvas, getattr(Qt.Key, 'Key_' + key))
            self.assertEqual(editor.canvas.tool, tool)
            self.assertTrue(editor.tool_buttons[tool].isChecked())
        editor.canvas.set_tool('text')
        self.assertTrue(editor.size_control.isVisible())
        self.assertFalse(editor.width_control.isVisible())
        editor.canvas.set_tool('redact')
        self.assertFalse(editor.colour_button.isVisible())
        menu_text = ' '.join(a.text() for a in editor.more_button.menu().actions())
        for feature in ('Save As', 'Save to History', 'Pin on Screen', 'OCR area'):
            self.assertIn(feature, menu_text)
        self.assertEqual(w.delay.count(), 4)
        self.assertTrue(any('active window' in a.text() for a in w.capture_menu.actions()))
        width = editor.canvas.width()
        editor.toggle_focus()
        APP.processEvents()
        self.assertGreater(editor.canvas.width(), width)
        self.assertFalse(editor.context.isVisible())
        editor.toggle_focus()
        self.assertTrue(editor.context.isVisible())

    def test_text_entry_and_paste_do_not_invoke_image_or_tool_actions(self):
        w = self.window
        w.set_document(white_image())
        w.show()
        w.editor.show_ocr('')
        APP.processEvents()
        QTest.keyClicks(w.editor.ocr_text, 'Plain text: CAPTURE')
        self.assertEqual(w.editor.canvas.tool, 'select')
        doc = w.doc
        APP.clipboard().setText(' copied text')
        QTest.keyClick(w.editor.ocr_text, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertIs(w.doc, doc)
        self.assertIn('copied text', w.doc.ocr_text)
        w.show_gallery()
        w.search.setFocus()
        QTest.keyClicks(w.search, 'capture')
        self.assertEqual(w.search.text(), 'capture')

    def test_small_window_fits_header_footer_and_settings_keep_all_preferences(self):
        w = self.window
        w.resize(900, 600)
        w.set_document(white_image())
        w.show()
        APP.processEvents()
        for widget in (w.brand, w.capture_button, w.command_button, w.editor.save_button, w.editor.ocr_button):
            point = widget.mapTo(w, widget.rect().bottomRight())
            self.assertLess(point.x(), w.width())
            self.assertLess(point.y(), w.height())
        dialog = SettingsDialog(w.settings, w)
        try:
            for key in ('auto_save', 'screenshots_dir', 'auto_copy', 'auto_history', 'save_dir', 'history_dir', 'ocr_path', 'ocr_data_dir', 'ocr_language', 'hotkey', 'jpeg_quality', 'close_to_tray'):
                self.assertIn(key, dialog.fields)
                self.assertEqual(dialog.values()[key], w.settings[key])
        finally:
            dialog.deleteLater()

    def test_command_palette_search_runs_after_modal_dialog_closes(self):
        calls = []
        dialog = CommandPalette([('Capture a region', lambda: calls.append(APP.activeModalWidget()), lambda: True),
                                 ('Unavailable action', lambda: None, lambda: False)], self.window)
        dialog.search.setText('region')
        self.assertEqual(dialog.results.count(), 1)
        QTimer.singleShot(10, dialog.run_selected)
        dialog.exec()
        APP.processEvents()
        self.assertEqual(calls, [None])
        dialog.deleteLater()

    def test_command_search_opens_from_ocr_text_and_arrow_keys_browse_results(self):
        w = self.window
        w.set_document(white_image())
        w.show()
        w.editor.show_ocr('Do not replace this text')
        APP.processEvents()
        observed = []
        def check_dialog():
            dialog = APP.activeModalWidget()
            observed.append(isinstance(dialog, CommandPalette))
            if isinstance(dialog, CommandPalette):
                QTest.keyClick(dialog.search, Qt.Key.Key_Down)
                observed.append(dialog.results.currentRow() == 1)
                dialog.reject()
        QTimer.singleShot(30, check_dialog)
        QTest.keyClick(w.editor.ocr_text, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(observed, [True, True])
        self.assertEqual(w.doc.ocr_text, 'Do not replace this text')
