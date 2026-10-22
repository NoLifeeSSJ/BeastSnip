import os
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QMessageBox
from beastsnip.app import MainWindow
from beastsnip.capture import RegionOverlay
from beastsnip.document import Annotation, Document
from beastsnip.projects import load_project
from beastsnip.scroll_capture import ScrollController
from test_document import APP, white_image
from test_scroll_capture import long_image
from test_workspace import settle
from test_updates import manifest


class Workflow21Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, {'BEASTSNIP_DATA_DIR': self.directory.name})
        environment.start(); self.addCleanup(environment.stop)
        self.window = MainWindow(smoke=True)
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.window.recovery.flush()
        settle(self.window)
        self.window.shutdown()
        APP.processEvents()

    def test_quick_capture_keeps_current_annotations_and_saves_a_batch(self):
        w = self.window
        w.set_document(white_image())
        w.doc.add(Annotation('text', [QPointF(10, 30)], text='Keep this editing session'))
        original, revision = w.doc, w.doc.revision
        w.settings.values['quick_capture'] = True
        w.settings.values['auto_save'] = False  # Quick Capture explicitly always saves.
        for n in range(5):
            w.captured(white_image(100 + n, 80 + n))
        settle(w)
        self.assertIs(w.doc, original)
        self.assertEqual(w.doc.revision, revision)
        self.assertEqual(len(w.doc.annotations), 1)
        self.assertEqual(len(list(Path(w.settings['screenshots_dir']).glob('*.png'))), 5)
        self.assertLessEqual(len(w.quick_store.items), 3)
        item = w.quick_store.items[-1]
        self.assertTrue(item.saved)
        self.assertTrue(w.quick_preview.open_button.isEnabled())
        w.quick_preview.copy_requested.emit(item)
        self.assertEqual(APP.clipboard().image().size(), item.image.size())
        w.quick_preview.pin_requested.emit(item)
        self.assertEqual(w.pins[-1].image.size(), item.image.size())
        with patch.object(w, 'confirm_discard', return_value=True):
            w.open_quick_capture(item)
        settle(w)
        self.assertIsNot(w.doc, original)
        self.assertEqual(w.autosave.path, item.path)

    def test_quick_save_failures_are_retained_and_retry_in_the_new_folder(self):
        w = self.window
        blocked = Path(self.directory.name) / 'blocked'; blocked.write_text('keep')
        w.settings.values['quick_capture'] = True
        w.settings.values['screenshots_dir'] = str(blocked / 'Screenshots')
        with self.assertLogs(level='ERROR'):
            w.captured(white_image()); w.captured(white_image(120, 90)); settle(w)
        self.assertEqual(len(w.quick_store.failures), 2)
        self.assertFalse(w.quick_preview.open_button.isEnabled())
        w.settings.values['screenshots_dir'] = str(Path(self.directory.name) / 'recovered')
        w.retry_quick_captures(); settle(w)
        self.assertFalse(w.quick_store.failures)
        self.assertEqual(len(list(Path(w.settings['screenshots_dir']).glob('*.png'))), 2)

    def test_editable_project_save_and_open_keep_objects_and_ocr_without_overwriting_a_png_hint(self):
        w = self.window
        w.set_document(white_image())
        w.doc.add(Annotation('arrow', [QPointF(10, 10), QPointF(50, 50)]))
        w.editor.show_ocr('Keep editable OCR')
        project = Path(self.directory.name) / 'editable.beastsnip'
        with patch('beastsnip.workflows.QFileDialog.getSaveFileName', return_value=(str(project), '')):
            w.save_editable_project()
        settle(w)
        self.assertTrue(project.exists())
        self.assertFalse(w.doc.dirty)
        w.set_document(white_image(120, 90))
        w.editor.show_ocr('Different text in the previous view')
        w.load_project_into_editor(project)
        self.assertEqual(w.doc.ocr_text, 'Keep editable OCR')
        self.assertEqual(w.editor.ocr_text.toPlainText(), 'Keep editable OCR')
        self.assertEqual(len(w.doc.annotations), 1)
        self.assertIsNone(w.autosave)
        self.assertEqual(w.project_path, project)

    def test_private_recovery_restores_the_latest_editable_document(self):
        w = self.window
        w.recovery.enabled = True
        w.set_document(white_image())
        w.doc.add(Annotation('redact', [QPointF(10, 10), QPointF(80, 80)]))
        w.editor.show_ocr('Text kept only in recovery')
        w.recovery.flush(); settle(w)
        restored, _ = load_project(w.recovery.path)
        self.assertEqual(restored.flatten().pixelColor(20, 20).name(), '#000000')
        self.assertEqual(restored.base.pixelColor(20, 20).name(), '#ffffff')
        w.recoverable_path = w.recovery.path
        with patch.object(w, 'confirm_discard', return_value=True):
            w.restore_recovery()
        self.assertEqual(len(w.doc.annotations), 1)
        self.assertEqual(w.doc.ocr_text, 'Text kept only in recovery')
        self.assertEqual(w.editor.ocr_text.toPlainText(), 'Text kept only in recovery')
        self.assertFalse(w.editor.ocr_panel.isHidden())
        self.assertIsNone(w.recoverable_path)

    def test_favourites_multi_select_rename_export_and_reversible_delete(self):
        w = self.window
        w.captured(white_image()); settle(w)
        active = w.autosave.path
        w.show_gallery(); settle(w)
        w.screenshots.setCurrentRow(0)
        w.toggle_favourites(); settle(w)
        self.assertIn('★', w.screenshots.item(0).text())
        self.assertEqual(w.selected_screenshot(), str(active))
        with patch('beastsnip.workflows.QInputDialog.getText', return_value=('Useful capture', True)):
            w.rename_selected_screenshot()
        settle(w)
        renamed = active.with_name('Useful capture.png')
        self.assertEqual(w.autosave.path, renamed)
        self.assertFalse(active.exists())
        w.doc.add(Annotation('redact', [QPointF(10, 10), QPointF(80, 80)])); settle(w)
        self.assertFalse(active.exists())
        w.refresh_screenshots(); settle(w); w.screenshots.setCurrentRow(0)
        exports = Path(self.directory.name) / 'exports'
        with patch('beastsnip.workflows.QFileDialog.getExistingDirectory', return_value=str(exports)):
            w.export_selected_screenshots()
        settle(w)
        self.assertTrue((exports / renamed.name).exists())
        with patch('beastsnip.workflows.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            w.delete_selected_screenshots()
        settle(w)
        self.assertFalse(renamed.exists()); self.assertIsNone(w.autosave)
        w.undo_library_delete(); settle(w)
        self.assertTrue(renamed.exists())

    def test_magnifier_uses_frozen_pixels_and_can_be_toggled_with_m(self):
        frozen = long_image(240, 400)
        session = SimpleNamespace(frozen=frozen, bounds=QRect(-100, -50, 240, 400),
            cursor_point=QPoint(0, 50), magnifier=True, selection=lambda: None, overlays=[])
        overlay = RegionOverlay(session, APP.primaryScreen(), session.bounds)
        self.addCleanup(overlay.close)
        session.overlays = [overlay]
        overlay.resize(360, 500); overlay.show(); APP.processEvents()
        before = overlay.grab().toImage()
        QTest.keyClick(overlay, Qt.Key.Key_M); APP.processEvents()
        after = overlay.grab().toImage()
        self.assertFalse(session.magnifier)
        self.assertNotEqual(before, after)
        self.assertEqual(session.frozen, frozen)

    def test_manual_scroll_controller_joins_real_frames_and_window_close_cancels(self):
        source = long_image()
        rect = QRect(0, 0, 240, 400)
        with patch('beastsnip.windows.window_at_point', return_value=123), patch('beastsnip.windows.window_rectangle', return_value=rect), patch('beastsnip.windows.escape_pressed', return_value=False), patch('beastsnip.windows.grab_pixels', side_effect=[source.copy(0, 0, 240, 400), source.copy(0, 170, 240, 400)]):
            controller = ScrollController(rect, automatic=False)
            results = []
            controller.captured.connect(results.append)
            controller.start(); QTest.qWait(230)
            controller.add_frame(); QTest.qWait(230)
            controller.finish()
            self.assertEqual(results[0], source.copy(0, 0, 240, 570))
            self.assertTrue(controller.done)
            second = ScrollController(rect, automatic=False)
            cancelled = QSignalSpy(second.cancelled)
            second.hud.show(); second.hud.close()
            self.assertTrue(second.done)
            self.assertEqual(cancelled.count(), 1)

    def test_finishing_a_scroll_waits_for_the_current_frame_without_another_wheel_event(self):
        rect, source = QRect(0, 0, 240, 400), long_image()
        with patch('beastsnip.windows.window_at_point', return_value=123), patch('beastsnip.windows.window_rectangle', return_value=rect), patch('beastsnip.windows.escape_pressed', return_value=False), patch('beastsnip.windows.grab_pixels', return_value=source.copy(0, 0, 240, 400)), patch('beastsnip.windows.scroll_at') as wheel:
            controller = ScrollController(rect, automatic=True)
            results = []; controller.captured.connect(results.append)
            controller.start(); controller.finish()
            QTest.qWait(300)
            self.assertTrue(controller.done)
            self.assertEqual(len(results), 1)
            wheel.assert_not_called()

    def test_update_centre_displays_release_notes_releases_lock_on_failed_launch_and_process_exit(self):
        w = self.window
        w.show_update_centre()
        dialog = w.update_dialog
        release = manifest(); release['version'] = '2.2.0'
        with patch('beastsnip.updates.fetch_manifest', return_value=release):
            dialog.check(); settle(w)
        self.assertIn('2.2.0', dialog.notes.toPlainText())
        self.assertTrue(dialog.install_button.isEnabled())
        with patch('beastsnip.updates.download_update', return_value=Path('verified.ps1')), patch('beastsnip.updates.launch_update', side_effect=OSError('PowerShell unavailable')):
            dialog.install(); settle(w)
        self.assertIn('PowerShell unavailable', dialog.status.text())
        self.assertFalse(w.updating)
        self.assertTrue(w.centralWidget().isEnabled())
        with patch('beastsnip.updates.download_update', return_value=Path('verified.ps1')), patch('beastsnip.updates.launch_update', return_value=Mock(poll=Mock(return_value=1))):
            dialog.install(); settle(w)
        self.assertTrue(w.updating)
        dialog.poll_status()
        self.assertFalse(w.updating)
        self.assertIn('exited', dialog.status.text())
        self.assertFalse(dialog.poll_timer.isActive())

    def test_update_centre_shows_rollback_and_restores_workspace_interaction(self):
        w = self.window
        w.show_update_centre()
        dialog = w.update_dialog
        self.assertTrue(w.prepare_update())
        with patch('beastsnip.app.SettingsDialog') as settings_dialog:
            w.open_settings()
            settings_dialog.assert_not_called()
        self.assertFalse(w.confirm_discard())
        dialog.busy = True
        path = Path(self.directory.name) / 'updates/status.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'state': 'rolled-back', 'message': 'Previous application and settings restored.'}))
        dialog.poll_status()
        self.assertFalse(w.updating)
        self.assertFalse(dialog.busy)
        self.assertTrue(w.centralWidget().isEnabled())
        self.assertIn('restored', dialog.status.text())
