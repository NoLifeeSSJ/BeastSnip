"""Application workflows for projects, quick capture and screenshot management."""
from datetime import datetime
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QKeySequence, QAction
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
    QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QToolButton, QWidget)

from .config import data_dir
from .library import LibraryIndex, export_pngs, path_key, rename_png, restore_trashed, trash_pngs
from .projects import RecoveryJournal, load_project, project_snapshot, save_project
from .quick_capture import QuickCaptureStore, QuickPreview
from .scroll_capture import ScrollController, ScrollSetupDialog
from .updates import UpdateCentre
from .ui import icon, tool_button
from .dialogs import PinnedWindow
from .storage import History


class WorkspaceWorkflows:
    def init_workflows(self, root):
        self.updating = False
        self.project_path = None
        self.library_index = LibraryIndex(data_dir() / 'library.sqlite3')
        self.library_limit, self.last_trash = 120, []
        self.library_busy = False
        self.quick_store = QuickCaptureStore(self.task, self)
        self.quick_store.changed.connect(self.quick_changed)
        self.quick_preview, self.scroll_controller, self.update_dialog = None, None, None
        self.recovery = RecoveryJournal(data_dir() / 'recovery' / 'session.beastsnip', self.task,
            enabled=self.settings['recover_session'] and not self.smoke, parent=self)
        self.recovery.state_changed.connect(self.update_autosave_ui)
        self.recoverable_path = self.recovery.path if self.recovery.path.exists() and not self.smoke else None
        self.recovery_bar = QWidget()
        self.recovery_bar.setObjectName('recoveryBanner')
        row = QHBoxLayout(self.recovery_bar)
        row.setContentsMargins(12, 8, 12, 8)
        title = QLabel('Your last editable session is ready to restore.')
        title.setWordWrap(True)
        row.addWidget(title, 1)
        for text, callback in [('Restore Session', self.restore_recovery), ('Dismiss', self.dismiss_recovery)]:
            button = QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
        root.insertWidget(1, self.recovery_bar)
        self.recovery_bar.setVisible(self.recoverable_path is not None)
        self.notice_bar = QWidget()
        self.notice_bar.setObjectName('recoveryBanner')
        row = QHBoxLayout(self.notice_bar)
        row.setContentsMargins(12, 8, 12, 8)
        self.notice_text = QLabel(); self.notice_text.setWordWrap(True)
        row.addWidget(self.notice_text, 1)
        self.notice_action = QPushButton(); self.notice_action.clicked.connect(self.run_notice_action)
        row.addWidget(self.notice_action)
        close = QPushButton('×'); close.setFixedWidth(30); close.clicked.connect(self.notice_bar.hide)
        row.addWidget(close)
        root.insertWidget(2, self.notice_bar)
        self.notice_bar.hide()
        self._notice_callback = None
        self.editor.ocr_text.textChanged.connect(self.recovery.schedule)
        self.library_selection_changed()

    def notice(self, text, action='', callback=None):
        self.notice_text.setText(text)
        self.notice_action.setText(action)
        self.notice_action.setVisible(bool(action and callback))
        self._notice_callback = callback
        self.notice_bar.show()

    def run_notice_action(self):
        if self._notice_callback:
            self._notice_callback()

    def preserve_previous_recovery(self):
        if self.recoverable_path == self.recovery.path and self.recovery.path.exists():
            archive = self.recovery.path.with_name(datetime.now().strftime('previous-%Y%m%d-%H%M%S-%f.beastsnip'))
            shutil.move(self.recovery.path, archive)
            self.recoverable_path = archive

    def restore_recovery(self):
        path = self.recoverable_path or self.recovery.path
        if self.doc and not self.confirm_discard():
            return
        try:
            doc, hint = load_project(path)
            self.recoverable_path = None
            self.recovery_bar.hide()
            self.set_document(doc)
            if doc.ocr_text:
                self.editor.show_ocr(doc.ocr_text)
            if hint:
                target = Path(hint)
                # Only our recovery record may resume a PNG, and only inside
                # the configured screenshots directory. Imported projects never do.
                if target.suffix.lower() == '.png' and target.resolve().parent == Path(self.settings['screenshots_dir']).resolve() and self.settings['auto_save']:
                    self.start_autosave(target)
            self.statusBar().showMessage('Restored the editable session, annotations and extracted text.', 12000)
        except Exception as error:
            self.error('Could not restore this session: ' + str(error))

    def dismiss_recovery(self):
        try:
            if self.recoverable_path:
                self.recoverable_path.unlink(missing_ok=True)
            self.recoverable_path = None
            self.recovery_bar.hide()
        except OSError as error:
            self.error(error)

    def clear_recovery(self, confirm=True):
        if self.recovery.busy:
            self.statusBar().showMessage('Wait for recovery saving to finish, then clear it.', 6000)
            return
        if confirm and QMessageBox.question(self, 'Clear recovery data', 'Remove automatic recovery sessions, including their original images? Your PNG screenshots and explicitly saved projects remain.') != QMessageBox.StandardButton.Yes:
            return
        try:
            self.recovery.clear()
            for path in self.recovery.path.parent.glob('previous-*.beastsnip'):
                path.unlink()
            self.recoverable_path = None
            self.recovery_bar.hide()
        except OSError as error:
            self.error(error)

    def save_editable_project(self):
        if not self.doc:
            return
        default = self.project_path or Path(self.settings['screenshots_dir']) / 'Projects' / datetime.now().strftime('BeastSnip_%Y-%m-%d_%H-%M-%S.beastsnip')
        path, _ = QFileDialog.getSaveFileName(self, 'Save editable project · includes original pixels and annotations', str(default), 'BeastSnip project (*.beastsnip)')
        if not path:
            return
        if not path.lower().endswith('.beastsnip'):
            path += '.beastsnip'
            if Path(path).exists() and QMessageBox.question(self, 'Replace project?', 'Replace the existing editable project?') != QMessageBox.StandardButton.Yes:
                return
        doc, revision, text = self.doc, self.doc.revision, self.doc.ocr_text
        snapshot = project_snapshot(doc, self.autosave.path if self.autosave else '')
        def completed(result, error):
            if error:
                self.error('Could not save the editable project: ' + error)
                return
            if self.doc is doc:
                self.project_path = Path(path)
                if doc.revision == revision:
                    doc.saved_revision, doc.saved_ocr_text = revision, text
                self.editor.update_state()
            self.statusBar().showMessage('Editable project saved. Share a flattened PNG when the original pixels should not be included.', 12000)
        self.task(lambda: save_project(path, snapshot), completed)

    def open_project(self, path=None):
        if not self.confirm_discard():
            return
        if not isinstance(path, (str, Path)):
            path = QFileDialog.getOpenFileName(self, 'Open editable project', self.settings['screenshots_dir'], 'BeastSnip project (*.beastsnip)')[0]
        if path:
            self.load_project_into_editor(path)

    def load_project_into_editor(self, path):
        try:
            doc, ignored_png_hint = load_project(path)
            self.set_document(doc)
            self.project_path = Path(path)
            if doc.ocr_text:
                self.editor.show_ocr(doc.ocr_text)
            self.statusBar().showMessage('Editable project opened. Annotations and recent undo/redo states are available.', 10000)
        except Exception as error:
            self.error('Could not open this editable project: ' + str(error))

    def set_quick_capture(self, enabled):
        old = self.settings['quick_capture']
        self.settings.values['quick_capture'] = bool(enabled)
        try:
            self.settings.save()
        except OSError as error:
            self.settings.values['quick_capture'] = old
            self.error(error)
        self.sync_capture_preferences()

    def sync_capture_preferences(self):
        for control in (self.quick_button, self.quick_action):
            control.blockSignals(True); control.setChecked(self.settings['quick_capture']); control.blockSignals(False)
        self.quick_button.setText('Quick on' if self.settings['quick_capture'] else 'Quick')
        self.quick_button.setToolTip('Quick Capture saves new snips as PNGs and keeps the current editor session. Use the preview to Open, Copy or Pin.')

    def captured_quickly(self, image):
        item = self.quick_store.capture(image, self.settings['screenshots_dir'])
        self.show_quick_preview(item)
        if self.settings['auto_copy']:
            self.copy_to_clipboard(image)
        if self.settings['auto_history']:
            directory, snapshot = self.settings['history_dir'], QImage(image)
            def store():
                history = History(directory)
                try:
                    return history.save(snapshot)
                finally:
                    history.close()
            self.task(store, lambda result, error: self.error(error) if error else self.refresh_gallery())

    def quick_changed(self, item):
        if self.quick_preview and self.quick_preview.item is item:
            self.quick_preview.display(item)
        if item.error:
            self.notice('A Quick Capture could not be saved. It is kept in memory until you retry or discard it.', 'Retry captures', self.retry_quick_captures)
        self.update_autosave_ui()
        if item.saved and self.stack.currentWidget() is self.home:
            self.refresh_screenshots()

    def show_quick_preview(self, item=None):
        item = item or (self.quick_store.items[-1] if self.quick_store.items else None)
        if item is None:
            return
        if not self.quick_preview:
            self.quick_preview = QuickPreview()
            self.quick_preview.open_requested.connect(self.open_quick_capture)
            self.quick_preview.copy_requested.connect(lambda capture: self.copy_to_clipboard(capture.image))
            self.quick_preview.pin_requested.connect(lambda capture: self.pin_snapshot(capture.image))
            self.quick_preview.retry_requested.connect(lambda capture: self.quick_store.save(capture, self.settings['screenshots_dir']))
        self.quick_preview.display(item)

    def open_quick_capture(self, item):
        if item and item.saved and self.confirm_discard():
            if self.quick_preview:
                self.quick_preview.hide()
            self.set_document(item.image)
            self.start_autosave(item.path)

    def retry_quick_captures(self):
        for item in self.quick_store.failures:
            self.quick_store.save(item, self.settings['screenshots_dir'])

    def pin_snapshot(self, image):
        pin = PinnedWindow(image)
        self.pins.append(pin)
        pin.destroyed.connect(lambda: self.pins.remove(pin) if pin in self.pins else None)
        pin.show()

    def start_scrolling_capture(self):
        if self.capture_busy or self.updating:
            return
        dialog = ScrollSetupDialog(self)
        try:
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
            self.scroll_options = (dialog.automatic.isChecked(), dialog.frames.value(), dialog.interval.value())
        finally:
            dialog.deleteLater()
        self.capture('scroll')

    def scrolling_region_selected(self, ignored_image):
        rect = self.capture_session.selected_rect
        self.capture_session.deleteLater()
        self.capture_session = None
        try:
            self.scroll_controller = ScrollController(rect, *self.scroll_options, parent=self)
            self.scroll_controller.captured.connect(self.captured)
            self.scroll_controller.cancelled.connect(self.capture_cancelled)
            self.scroll_controller.start()
        except Exception as error:
            self.capture_cancelled()
            self.bring_forward()
            self.error(error)

    def add_library_filters(self, layout):
        row = QHBoxLayout()
        self.date_filter = QComboBox()
        for label, value in [('All dates', 'all'), ('Today', 'today'), ('Last 7 days', 'week'), ('Last 30 days', 'month')]:
            self.date_filter.addItem(label, value)
        self.date_filter.currentIndexChanged.connect(self.reset_library_filter)
        row.addWidget(self.date_filter)
        self.favourites_filter = QCheckBox('Favourites only')
        self.favourites_filter.toggled.connect(self.reset_library_filter)
        row.addWidget(self.favourites_filter)
        row.addStretch()
        hint = QLabel('Ctrl / Shift to select several')
        hint.setObjectName('muted')
        row.addWidget(hint)
        layout.addLayout(row)

    def add_library_actions(self, layout):
        self.screenshots.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.screenshots.itemSelectionChanged.connect(self.library_selection_changed)
        self.screenshots.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screenshots.customContextMenuRequested.connect(self.screenshot_context_menu)
        row = QHBoxLayout()
        self.library_open = tool_button('pen', 'Open', self.open_screenshot)
        self.library_copy = tool_button('copy', 'Copy', self.copy_screenshot)
        self.library_favourite = tool_button('star', 'Favourite', self.toggle_favourites)
        self.library_export = tool_button('folder', 'Export', self.export_selected_screenshots)
        for button in (self.library_open, self.library_copy, self.library_favourite, self.library_export):
            row.addWidget(button)
        more = tool_button('more', 'More')
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction('Rename screenshot (F2)', self.rename_selected_screenshot)
        menu.addAction('Move selected screenshots to Trash (Delete)', self.delete_selected_screenshots)
        menu.addAction('Undo last screenshot deletion', self.undo_library_delete)
        menu.addAction('Open Screenshots folder', self.open_screenshots_folder)
        more.setMenu(menu); row.addWidget(more)
        self.library_selection = QLabel(); self.library_selection.setObjectName('muted')
        row.addWidget(self.library_selection, 1)
        self.load_more = QPushButton('Load more')
        self.load_more.clicked.connect(self.load_more_screenshots)
        self.load_more.hide()
        row.addWidget(self.load_more)
        layout.addLayout(row)
        for sequence, callback in [('F2', self.rename_selected_screenshot), ('Delete', self.delete_selected_screenshots)]:
            action = QAction(self.screenshots)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.screenshots.addAction(action)

    def reset_library_filter(self, *args):
        self.library_limit = 120
        self.refresh_screenshots()

    def load_more_screenshots(self):
        self.library_limit += 120
        self.refresh_screenshots()

    def selected_screenshots(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.screenshots.selectedItems()]

    def library_selection_changed(self):
        count = len(self.screenshots.selectedItems())
        self.library_selection.setText(f'{count} selected' if count else 'Select a snip')
        self.library_open.setEnabled(count == 1)
        self.library_copy.setEnabled(count == 1)
        self.library_favourite.setEnabled(count > 0)
        self.library_export.setEnabled(count > 0)

    def screenshot_context_menu(self, point):
        menu = QMenu(self.screenshots)
        for label, callback in [('Open in Editor', self.open_screenshot), ('Copy image', self.copy_screenshot),
            ('Toggle favourites', self.toggle_favourites), ('Rename…', self.rename_selected_screenshot),
            ('Export selected…', self.export_selected_screenshots), ('Move selected to Trash', self.delete_selected_screenshots)]:
            menu.addAction(label, callback)
        menu.exec(self.screenshots.viewport().mapToGlobal(point))

    def toggle_favourites(self):
        paths = self.selected_screenshots()
        if paths:
            try:
                favourites = self.library_index.favourites()
                self.library_index.set_favourite(paths, not all(path_key(path) in favourites for path in paths))
                self.refresh_screenshots()
            except Exception as error:
                self.error(error)

    def prepare_library_mutation(self, paths):
        if self.library_busy:
            self.statusBar().showMessage('Wait for the current library operation to finish.', 6000)
            return False
        if self.autosave and path_key(self.autosave.path) in {path_key(p) for p in paths}:
            if not self.finish_autosaves():
                return False
        return True

    def rename_selected_screenshot(self):
        paths = self.selected_screenshots()
        if len(paths) != 1 or not self.prepare_library_mutation(paths):
            return
        name, ok = QInputDialog.getText(self, 'Rename screenshot', 'Filename', text=Path(paths[0]).stem)
        if not ok:
            return
        try:
            old = Path(paths[0]); target = rename_png(old, name)
            self.library_index.move(old, target)
            if self.autosave and path_key(self.autosave.path) == path_key(old):
                self.autosave.path = target
                self.recovery.png_path = str(target); self.recovery.schedule()
            self.refresh_screenshots()
        except Exception as error:
            self.error(error)

    def export_selected_screenshots(self):
        paths = self.selected_screenshots()
        if not paths or not self.prepare_library_mutation(paths):
            return
        directory = QFileDialog.getExistingDirectory(self, 'Export selected PNG screenshots', self.settings['save_dir'])
        if not directory:
            return
        self.library_busy = True
        def completed(result, error):
            self.library_busy = False
            if error:
                self.error(error)
            else:
                saved, failures = result
                self.notice(f'Exported {len(saved)} PNG screenshot(s).' + ('\n' + '\n'.join(failures[:4]) if failures else ''))
        self.task(lambda: export_pngs(paths, directory), completed)

    def delete_selected_screenshots(self):
        paths = self.selected_screenshots()
        if not paths or not self.prepare_library_mutation(paths):
            return
        if QMessageBox.question(self, 'Move screenshots to Trash', f'Move {len(paths)} selected PNG screenshot(s) to BeastSnip Trash? You can undo this deletion. Saved projects and Saved History remain.') != QMessageBox.StandardButton.Yes:
            return
        self.library_busy = True
        directory = self.settings['screenshots_dir']
        def completed(result, error):
            self.library_busy = False
            if error:
                self.error(error)
                return
            entries, failures = result
            self.last_trash = entries
            if self.autosave and path_key(self.autosave.path) in {path_key(e['source']) for e in entries}:
                session, self.autosave = self.autosave, None
                session.retire()
                self.doc.saved_revision = -1
                self.recovery.png_path = ''; self.recovery.schedule()
                self.autosave_changed()
            self.refresh_screenshots()
            self.notice(f'Moved {len(entries)} screenshot(s) to Trash.' + ('\n' + '\n'.join(failures[:4]) if failures else ''), 'Undo', self.undo_library_delete)
        self.task(lambda: trash_pngs(paths, directory), completed)

    def undo_library_delete(self):
        if not self.last_trash or self.library_busy:
            return
        self.library_busy = True
        entries = self.last_trash[:]
        def completed(result, error):
            self.library_busy = False
            if error:
                self.error(error)
                return
            restored, failures = result
            for old, new in restored:
                if old != new:
                    self.library_index.move(old, new)
            restored_keys = {old for old, new in restored}
            self.last_trash = [e for e in entries if e['source'] not in restored_keys]
            self.refresh_screenshots()
            self.notice(f'Restored {len(restored)} screenshot(s).' + ('\n' + '\n'.join(failures[:4]) if failures else ''))
        self.task(lambda: restore_trashed(entries), completed)

    def show_update_centre(self):
        if not self.update_dialog:
            self.update_dialog = UpdateCentre(self)
        self.update_dialog.show()
        self.update_dialog.raise_()
        self.update_dialog.activateWindow()

    def prepare_update(self):
        if not self.finish_autosaves() or self.tasks or self.ocr_job:
            return False
        if self.recovery.error or self.quick_store.failures:
            self.notice('Resolve the pending recovery or Quick Capture save error before updating.', 'Retry saves', self.retry_autosaves)
            return False
        if self.doc and self.doc.dirty and not self.recovery.enabled and not self.confirm_discard():
            return False
        self.updating = True
        self.centralWidget().setEnabled(False)
        return True

    def end_update(self):
        self.updating = False
        self.centralWidget().setEnabled(True)
