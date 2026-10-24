from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

from beastsnip.app import MainWindow
from beastsnip.changelog import parse_changelog
from beastsnip.document import Annotation, Document, encode_image
from beastsnip.editor import AnnotationItem
from beastsnip.projects import load_project, project_snapshot, save_project
from beastsnip.release_history import ReleaseHistory, load_history
from beastsnip.style import STYLE
from beastsnip.ui import icon
from beastsnip import windows
from test_document import APP, white_image
from test_workspace import settle


class Drawing211Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {'BEASTSNIP_DATA_DIR': self.directory.name}); env.start(); self.addCleanup(env.stop)
        style = APP.styleSheet(); APP.setStyleSheet(STYLE); self.addCleanup(APP.setStyleSheet, style)
        self.window = MainWindow(smoke=True); self.addCleanup(self.cleanup_window)
        self.window.resize(1000, 720); self.window.set_document(white_image()); self.window.show()
        APP.processEvents()

    def cleanup_window(self):
        self.window.editor.colour_palette.hide(); self.window.editor.style_popup.hide()
        settle(self.window); self.window.shutdown(); APP.processEvents()

    def test_new_tools_draw_real_annotations_with_shift_and_remember_separate_styles(self):
        editor, doc = self.window.editor, self.window.doc
        canvas = editor.canvas
        for tool in ('pen', 'brush', 'line', 'round_rect'):
            canvas.set_tool(tool)
            start = canvas.mapFromScene(QPointF(30, 40)); end = canvas.mapFromScene(QPointF(160, 110))
            QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(80, 80)))
            QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, end)
            self.assertEqual(doc.annotations[-1].kind, tool)
        rounded = doc.annotations[-1]
        delta = rounded.points[-1] - rounded.points[0]
        self.assertAlmostEqual(abs(delta.x()), abs(delta.y()), delta=.5)
        self.assertEqual(doc.annotations[1].width, 20)
        canvas.set_tool('pen'); editor.change_property('width', 9); editor.change_property('line_style', 'dash')
        canvas.set_tool('brush'); self.assertEqual(canvas.stroke_width, 20); self.assertEqual(canvas.line_style, 'solid')
        canvas.set_tool('pen'); self.assertEqual(canvas.stroke_width, 9); self.assertEqual(canvas.line_style, 'dash')
        saved = json.loads(self.window.settings.path.read_text())
        self.assertEqual(saved['drawing_preferences']['pen']['width'], 9)
        self.assertNotEqual(encode_image(doc.flatten()), encode_image(doc.base))

    def test_colour_style_edits_keep_selection_are_undoable_and_save_to_same_png(self):
        w, editor = self.window, self.window.editor
        w.start_autosave(); settle(w); path = w.autosave.path
        w.doc.add(Annotation('line', [QPointF(20, 60), QPointF(200, 60)], '#ff0000', 6)); settle(w)
        item = next(i for i in editor.canvas.scene().items() if isinstance(i, AnnotationItem))
        item.setSelected(True)
        editor.choose_colour(); editor.colour_palette.hex.setText('#3366FF'); editor.colour_palette.apply_hex()
        self.assertEqual(editor.canvas.selected_index(), 0)
        editor.choose_style()
        combo = editor.style_popup.combos['line_style']; combo.setCurrentIndex(combo.findData('dash'))
        editor.style_popup.opacity.setValue(50)
        self.assertEqual(editor.canvas.selected_index(), 0)
        self.assertEqual(w.doc.annotations[0].color, '#3366ff')
        self.assertEqual(w.doc.annotations[0].opacity, 50)
        editor.style_popup.hide(); settle(w)
        self.assertEqual(w.autosave.path, path)
        self.assertEqual(QImage(str(path)), w.doc.flatten())
        w.doc.undo(); self.assertEqual(w.doc.annotations[0].opacity, 100)
        w.doc.undo(); self.assertEqual(w.doc.annotations[0].line_style, 'solid')
        w.doc.undo(); self.assertEqual(w.doc.annotations[0].color, '#ff0000')

    def test_eraser_groups_drag_undo_and_saves_after_an_intermediate_write(self):
        w = self.window; canvas = w.editor.canvas
        for x in (35, 125):
            w.doc.add(Annotation('filled', [QPointF(x, 60), QPointF(x + 40, 100)], '#ff0000'))
        w.start_autosave(); settle(w); before = len(w.doc.undo_stack)
        original = QImage(w.doc.base)
        canvas.set_tool('eraser')
        first = canvas.mapFromScene(QPointF(50, 75)); second = canvas.mapFromScene(QPointF(140, 75))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=first)
        self.assertEqual(len(w.doc.annotations), 1)
        settle(w)  # A long gesture may already have saved its first change.
        QTest.mouseMove(canvas.viewport(), second)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=second)
        settle(w)
        self.assertEqual(w.doc.annotations, [])
        self.assertEqual(QImage(str(w.autosave.path)), original)
        self.assertEqual(len(w.doc.undo_stack), before + 1)
        w.doc.undo(); self.assertEqual(len(w.doc.annotations), 2)
        w.doc.redo(); self.assertEqual(w.doc.annotations, [])
        self.assertEqual(w.doc.base, original)
        w.doc.undo()
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=first)
        self.assertEqual(len(w.doc.annotations), 1)
        w.doc.undo()  # Undo during a held gesture cancels further erasing.
        QTest.mouseMove(canvas.viewport(), second)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=second)
        self.assertEqual(len(w.doc.annotations), 2)

    def test_patterns_opacity_soft_fill_smoothing_and_redaction_render_correct_pixels(self):
        def render(item):
            doc = Document(white_image()); doc.add(item); return doc.flatten()
        line = Annotation('line', [QPointF(20, 60), QPointF(210, 60)], '#000000', 4)
        solid = render(line); line.line_style = 'dash'; dashed = render(line)
        self.assertNotEqual(solid, dashed)
        self.assertTrue(any(dashed.pixelColor(x, 60).name() == '#ffffff' and solid.pixelColor(x, 60).name() == '#000000' for x in range(30, 200)))
        shape = Annotation('round_rect', [QPointF(20, 20), QPointF(120, 120)], '#ff0000', fill_style='solid', opacity=50)
        self.assertAlmostEqual(render(shape).pixelColor(60, 60).green(), 127, delta=1)
        shape.opacity = 100; shape.fill_style = 'soft'
        self.assertAlmostEqual(render(shape).pixelColor(60, 60).green(), 191, delta=1)
        pen = Annotation('pen', [QPointF(20, 20), QPointF(60, 100), QPointF(100, 20), QPointF(180, 100)])
        sharp = render(pen); pen.smooth = True; self.assertNotEqual(sharp, render(pen))
        redaction = Annotation('redact', [QPointF(20, 20), QPointF(120, 120)], '#ffffff', opacity=5, line_style='dot', fill_style='soft')
        result = render(redaction)
        for y in range(20, 120):
            for x in range(20, 120): self.assertEqual(result.pixelColor(x, y).name(), '#000000')

    def test_styled_projects_preserve_pixels_undo_and_legacy_projects_keep_appearance(self):
        old, _ = load_project(Path(__file__).parent / 'fixtures/v210-editable.beastsnip')
        self.assertEqual(old.ocr_text, 'Legacy 2.1 project')
        self.assertFalse(old.annotations[0].smooth); self.assertEqual(old.annotations[0].opacity, 100)
        doc = Document(white_image())
        for kind in ('brush', 'line', 'round_rect', 'arrow'):
            doc.add(Annotation(kind, [QPointF(25, 30), QPointF(190, 125)], '#dd3377', 10,
                opacity=65, line_style='dash', cap='square', fill_style='soft', arrow_heads='both', smooth=True))
        path = Path(self.directory.name) / 'styled.beastsnip'
        save_project(path, project_snapshot(doc))
        restored, _ = load_project(path)
        self.assertEqual(restored.flatten(), doc.flatten())
        self.assertEqual(restored.annotations, doc.annotations)
        restored.undo(); self.assertEqual(len(restored.annotations), 3)
        restored.redo(); self.assertEqual(restored.flatten(), doc.flatten())
        with zipfile.ZipFile(path) as archive: self.assertEqual(json.loads(archive.read('project.json'))['schema'], 2)

    def test_small_window_size_fields_and_popovers_fit_and_gear_is_centred(self):
        w, editor = self.window, self.window.editor
        w.resize(900, 600); editor.canvas.set_tool('pen'); APP.processEvents()
        field = editor.width_control
        self.assertGreaterEqual(field.lineEdit().width(), field.fontMetrics().horizontalAdvance('80 px') + 6)
        for widget in (editor.colour_button, field, editor.style_button, editor.delete_button):
            point = widget.mapTo(w, widget.rect().bottomRight())
            self.assertLess(point.x(), w.width()); self.assertLess(point.y(), w.height())
        for tool in ('pen', 'brush', 'highlight', 'arrow', 'rect', 'round_rect', 'filled', 'text'):
            editor.canvas.set_tool(tool); editor.choose_style(); APP.processEvents()
            popup = editor.style_popup
            self.assertLessEqual(popup.width(), popup.screen().availableGeometry().width())
            self.assertLessEqual(popup.height(), popup.screen().availableGeometry().height() - 10)
            self.assertTrue(popup.preview.isVisible())
            popup.scroll.ensureWidgetVisible(popup.reset_button); APP.processEvents()
            bottom = popup.reset_button.mapTo(popup.scroll.viewport(), popup.reset_button.rect().bottomRight())
            self.assertLessEqual(bottom.y(), popup.scroll.viewport().height())
            QTest.mouseClick(popup.reset_button, Qt.MouseButton.LeftButton)
            popup.hide()
        image = icon('settings').pixmap(96, 96).toImage()
        pixels = [(x, y) for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x, y).alpha() > 32]
        xs, ys = [p[0] for p in pixels], [p[1] for p in pixels]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, (image.width() - 1) / 2, delta=1)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, (image.height() - 1) / 2, delta=1)

    def test_version_history_covers_all_releases_searches_and_copies_selected_notes(self):
        history = load_history()
        self.assertEqual([r['version'] for r in history], ['2.1.2', '2.1.1', '2.1.0', '2.0.1', '2.0.0', '1.0.3', '1.0.2', '1.0.1', '1.0.0'])
        dialog = ReleaseHistory(self.window); self.addCleanup(dialog.close); dialog.show()
        self.assertIn('2.1.2', dialog.reader.toPlainText())
        self.assertIn('LEN G25-10', dialog.reader.toPlainText())
        dialog.search.setText('396'); self.assertEqual(len(dialog.matches), 1)
        self.assertEqual(dialog.matches[0]['version'], '2.0.1')
        dialog.copy_notes(); self.assertIn('396', APP.clipboard().text())
        dialog.search.clear(); dialog.versions.setCurrentRow(0)
        for release in history: self.assertIn('BeastSnip ' + release['version'], dialog.reader.toPlainText())
        dialog.search.setText('no such feature xxyz'); self.assertFalse(dialog.copy.isEnabled())
        self.assertIn('No matching', dialog.reader.toPlainText())

    def test_windows_app_identity_uses_its_own_stable_id_and_reports_hresult_failure(self):
        function = Mock(return_value=0)
        with patch.object(windows, 'IS_WINDOWS', True), patch.object(windows.ctypes, 'WinDLL', return_value=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=function), create=True):
            self.assertTrue(windows.set_app_identity())
            function.assert_called_once_with('NoLifeeSSJ.BeastSnip.Desktop')
            function.return_value = -1
            with self.assertRaises(OSError): windows.set_app_identity()
