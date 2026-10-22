from datetime import datetime
import logging
from pathlib import Path
import sys

from PySide6.QtCore import (QDir, QEvent, QLockFile, QObject, QSize, Qt, QThreadPool,
    QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QImage, QImageReader, QKeySequence, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget, QLineEdit,
    QButtonGroup, QTabWidget, QToolButton, QWidgetAction, QSizePolicy)

from .capture import RegionSession
from .config import Settings, data_dir, resource
from .dialogs import PinnedWindow, SettingsDialog
from .document import Document, save_image
from .editor import Editor, TOOLS
from .autosave import AutosaveSession, capture_path
from .ui import CommandPalette, icon, tool_button
from .ocr import OCRJob, find_tesseract
from .storage import History
from .library import date_matches, path_key
from .workflows import WorkspaceWorkflows
from .style import STYLE
from .tasks import Task
from .windows import WindowsIntegration
from . import windows
from . import __version__


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        import hashlib
        name = "BeastSnip-" + hashlib.sha256(str(data_dir().resolve()).encode()).hexdigest()[:20]
        self.name = name
        data_dir().mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(data_dir() / "instance.lock"))
        self.server = None

    def acquire(self):
        if not self.lock.tryLock(0):
            socket = QLocalSocket(self)
            socket.connectToServer(self.name)
            if socket.waitForConnected(2000):
                socket.write(b"activate")
                socket.flush()
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
                return False
            raise RuntimeError("Another BeastSnip instance is starting or not responding. Wait a moment and retry.")
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.connection)
        if not self.server.listen(self.name):
            raise RuntimeError("Could not start the single-instance notification server.")
        return True

    def connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
            self.activated.emit()

    def close(self):
        if self.server:
            self.server.close()
        self.lock.unlock()


class MainWindow(WorkspaceWorkflows, QMainWindow):
    def __init__(self, smoke=False):
        super().__init__()
        self.smoke = smoke
        self.settings = Settings()
        self.history = History(self.settings["history_dir"])
        self.doc = None
        self.pins, self.tasks = [], []
        self.ocr_job, self.capture_session = None, None
        self.capture_busy, self.history_busy, self.export_busy, self.quitting = False, False, False, False
        self.ocr_generation = None
        self.autosave = None
        self.autosaves = []
        self._screenshot_loading = False
        self._refresh_again = False
        self.setWindowTitle(f"BeastSnip {__version__}")
        self.setWindowIcon(QIcon(str(resource("beastsnip.ico"))))
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 8)
        root.setSpacing(12)
        header = QWidget()
        header.setObjectName('appHeader')
        nav = QHBoxLayout(header)
        nav.setContentsMargins(10, 8, 10, 8)
        nav.setSpacing(8)
        self.brand = tool_button('library', 'BeastSnip')
        self.brand.setObjectName('brand')
        self.brand.setIcon(self.windowIcon())
        self.brand.setIconSize(QSize(30, 30))
        self.brand.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        brand_menu = QMenu(self.brand)
        brand_menu.addAction(icon('library'), 'Screenshot library', self.show_gallery)
        brand_menu.addAction(icon('folder'), 'Open Screenshots folder', self.open_screenshots_folder)
        brand_menu.addSeparator()
        brand_menu.addAction(icon('settings'), 'Preferences', self.open_settings)
        brand_menu.addAction(icon('help'), 'Keyboard shortcuts', self.show_shortcuts)
        brand_menu.addAction(icon('project'), 'Open Editable Project…', self.open_project)
        brand_menu.addAction(icon('recovery'), 'Restore Last Session', self.restore_recovery)
        brand_menu.addAction('Clear Automatic Recovery Data…', lambda: self.clear_recovery())
        brand_menu.addAction(icon('updates'), 'Update Centre', self.show_update_centre)
        brand_menu.addAction(icon('history'), 'Version History · all updates', self.show_changelog)
        brand_menu.addAction('About BeastSnip', self.show_about)
        brand_menu.addSeparator()
        brand_menu.addAction('Quit BeastSnip', self.quit_app)
        self.brand.setMenu(brand_menu)
        nav.addWidget(self.brand)
        self.workspace_tabs = QButtonGroup(self)
        self.workspace_tabs.setExclusive(True)
        self.library_nav = tool_button('library', 'Library', self.show_gallery)
        self.editor_nav = tool_button('pen', 'Editor', self.resume_editor)
        for button in (self.library_nav, self.editor_nav):
            button.setObjectName('workspaceTab')
            button.setCheckable(True)
            self.workspace_tabs.addButton(button)
            nav.addWidget(button)
        self.library_nav.setChecked(True)
        self.editor_nav.setEnabled(False)
        nav.addStretch()
        self.capture_button = tool_button('capture', 'New Snip', lambda: self.capture('region'))
        self.capture_button.setObjectName('primary')
        self.capture_button.setToolTip('Capture a region · ' + self.settings['hotkey'] + '\nUse the arrow for window, monitor and delay options')
        self.capture_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.capture_button.setProperty('split', True)
        self.capture_menu = QMenu(self.capture_button)
        self.capture_menu.addAction(icon('capture'), 'Capture a region', lambda: self.capture('region'))
        self.capture_menu.addAction(icon('window'), 'Capture active window', lambda: self.capture('window'))
        self.capture_menu.addAction(icon('monitor'), 'Capture selected monitor', lambda: self.capture('monitor'))
        self.capture_menu.addAction(icon('scroll'), 'Scrolling capture…', self.start_scrolling_capture)
        self.capture_menu.addSeparator()
        self.quick_action = self.capture_menu.addAction('Quick Capture · always save PNG, keep the editor')
        self.quick_action.setCheckable(True)
        self.quick_action.setChecked(self.settings['quick_capture'])
        self.quick_action.toggled.connect(self.set_quick_capture)
        self.capture_menu.addAction('Show latest capture preview', self.show_quick_preview)
        self.capture_menu.addSeparator()
        options = QWidget()
        option_layout = QVBoxLayout(options)
        option_layout.setContentsMargins(14, 10, 14, 10)
        option_layout.addWidget(QLabel('Monitor'))
        self.monitor = QComboBox()
        self.monitor.setMinimumWidth(240)
        self.refresh_monitors()
        option_layout.addWidget(self.monitor)
        option_layout.addWidget(QLabel('Capture delay'))
        self.delay = QComboBox()
        for delay in (0, 3, 5, 10):
            self.delay.addItem('No delay' if delay == 0 else f'{delay} seconds', delay)
        self.delay.setCurrentIndex((0, 3, 5, 10).index(self.settings['delay']))
        self.delay.currentIndexChanged.connect(self.delay_changed)
        option_layout.addWidget(self.delay)
        option_action = QWidgetAction(self.capture_menu)
        option_action.setDefaultWidget(options)
        self.capture_menu.addAction(option_action)
        self.capture_button.setMenu(self.capture_menu)
        nav.addWidget(self.capture_button)
        self.quick_button = tool_button('quick', 'Quick')
        self.quick_button.setCheckable(True)
        self.quick_button.setObjectName('quickToggle')
        self.quick_button.toggled.connect(self.set_quick_capture)
        nav.addWidget(self.quick_button)
        self.command_button = tool_button('search', 'Find action (Ctrl+K)', self.show_commands, icon_only=True)
        nav.addWidget(self.command_button)
        nav.addWidget(tool_button('folder', 'Open image (Ctrl+O)', self.open_image, icon_only=True))
        nav.addWidget(tool_button('settings', 'Preferences', self.open_settings, icon_only=True))
        root.addWidget(header)
        self.save_warning = QWidget()
        self.save_warning.setObjectName('warningBanner')
        warning_layout = QHBoxLayout(self.save_warning)
        warning_layout.setContentsMargins(12, 8, 12, 8)
        self.save_warning_text = QLabel()
        self.save_warning_text.setWordWrap(True)
        warning_layout.addWidget(self.save_warning_text, 1)
        self.add_button(warning_layout, 'Retry save', self.retry_autosaves)
        self.add_button(warning_layout, 'Preferences', self.open_settings)
        self.save_warning.hide()
        root.addWidget(self.save_warning)
        self.stack = QStackedWidget()
        self.home = QWidget()
        home_layout = QVBoxLayout(self.home)
        home_layout.setContentsMargins(4, 0, 4, 0)
        home_layout.setSpacing(14)
        welcome = QWidget()
        welcome.setObjectName('welcomeCard')
        welcome_row = QHBoxLayout(welcome)
        welcome_row.setContentsMargins(22, 20, 22, 20)
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(64, 64))
        welcome_row.addWidget(logo)
        intro = QVBoxLayout()
        title = QLabel('A little capture. A clearer picture.')
        title.setObjectName('welcomeTitle')
        intro.addWidget(title)
        self.library_description = QLabel()
        self.library_description.setObjectName('muted')
        self.library_description.setWordWrap(True)
        intro.addWidget(self.library_description)
        welcome_row.addLayout(intro, 1)
        self.add_button(welcome_row, 'Paste Image', self.paste_image)
        home_layout.addWidget(welcome)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText('Search screenshots, or titles, tags and OCR in Saved History…')
        self.search.textChanged.connect(self.refresh_library)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(tool_button('folder', 'Screenshots folder', self.open_screenshots_folder))
        search_row.addWidget(tool_button('redo', 'Refresh (F5)', self.refresh_library, icon_only=True))
        home_layout.addLayout(search_row)
        self.library_tabs = QTabWidget()
        screenshot_page = QWidget()
        screenshot_layout = QVBoxLayout(screenshot_page)
        self.screenshot_count = QLabel('Your captures will appear here.')
        self.screenshot_count.setObjectName('muted')
        screenshot_layout.addWidget(self.screenshot_count)
        self.add_library_filters(screenshot_layout)
        self.screenshots = QListWidget()
        self.configure_gallery(self.screenshots)
        self.screenshots.itemDoubleClicked.connect(lambda item: self.open_screenshot())
        screenshot_layout.addWidget(self.screenshots, 1)
        self.add_library_actions(screenshot_layout)
        self.library_tabs.addTab(screenshot_page, 'Screenshots')
        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        self.empty = QLabel('Keep selected captures here with Save to History.\nHistory also stores searchable titles, tags and extracted text.')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setObjectName('emptyState')
        history_layout.addWidget(self.empty)
        self.gallery = QListWidget()
        self.configure_gallery(self.gallery)
        self.gallery.itemDoubleClicked.connect(lambda item: self.open_history())
        history_layout.addWidget(self.gallery, 1)
        gallery_actions = QHBoxLayout()
        for label, callback in [('Open in Editor', self.open_history), ('Copy Image', self.copy_history),
                                ('Edit Title / Tags', self.rename_history), ('Open Folder', self.history_folder)]:
            self.add_button(gallery_actions, label, callback)
        history_more = tool_button('more', 'More')
        history_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        history_menu = QMenu(history_more)
        history_menu.addAction('Delete selected history item', self.delete_history)
        history_menu.addAction('Clear History', self.clear_history)
        history_more.setMenu(history_menu)
        gallery_actions.addWidget(history_more)
        gallery_actions.addStretch()
        history_layout.addLayout(gallery_actions)
        self.library_tabs.addTab(history_page, 'Saved History')
        self.library_tabs.currentChanged.connect(self.refresh_library)
        home_layout.addWidget(self.library_tabs, 1)
        self.stack.addWidget(self.home)
        self.editor = Editor()
        self.editor.load_preferences(self.settings['drawing_preferences'])
        self.editor.preferences_changed.connect(self.save_drawing_preferences)
        self.editor.copy_requested.connect(self.copy_image)
        self.editor.save_requested.connect(self.export_image)
        self.editor.quicksave_requested.connect(self.quick_save)
        self.editor.folder_requested.connect(self.open_screenshots_folder)
        self.editor.history_requested.connect(self.save_history)
        self.editor.pin_requested.connect(self.pin_image)
        self.editor.ocr_requested.connect(self.extract_text)
        self.editor.project_requested.connect(self.save_editable_project)
        self.stack.addWidget(self.editor)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.init_workflows(root)
        self.sync_capture_preferences()
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("BeastSnip · local screenshots")
        menu = QMenu(self)
        for label, callback in [("New region capture", lambda: self.capture("region")),
                                ("Capture active window", lambda: self.capture("window")),
                                ("Capture selected monitor", lambda: self.capture("monitor")),
                                ("Scrolling capture", self.start_scrolling_capture),
                                ("Show latest preview", self.show_quick_preview), ("Update Centre", self.show_update_centre),
                                ("Open gallery", self.show_gallery), ("Settings", self.open_settings), ("Quit BeastSnip", self.quit_app)]:
            menu.addAction(label, callback)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.bring_forward() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if not smoke and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.integration = WindowsIntegration(QApplication.instance())
        self.integration.triggered.connect(lambda: self.capture("region"))
        self.hotkey_warning = self.integration.register(self.settings["hotkey"]) if not smoke else ""
        self.capture_timer = QTimer(self)
        self.capture_timer.setSingleShot(True)
        self.capture_timer.timeout.connect(self.perform_capture)
        self.refresh_library()
        self.update_autosave_ui()
        self.stack.currentChanged.connect(self.workspace_changed)
        for sequence, callback in [("Ctrl+K", self.show_commands), ("Ctrl+O", self.open_image),
                                   ("Ctrl+V", self.paste_image), ("F1", self.show_shortcuts), ("F5", self.refresh_library)]:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)
        QApplication.instance().screenAdded.connect(lambda screen: self.refresh_monitors())
        QApplication.instance().screenRemoved.connect(lambda screen: self.refresh_monitors())
        if self.hotkey_warning:
            self.statusBar().showMessage(self.hotkey_warning)
        else:
            self.statusBar().showMessage("Ready · Images and OCR stay local · " + self.settings["hotkey"] + " for region capture")

    @staticmethod
    def add_button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def error(self, message):
        logging.error("Operation failed; see on-screen message")
        QMessageBox.warning(self, "BeastSnip", str(message))

    def save_drawing_preferences(self, values):
        self.settings.values['drawing_preferences'] = values
        try:
            self.settings.save()
        except OSError:
            self.statusBar().showMessage('The drawing style is active, but could not be saved for next time.', 8000)

    def show_changelog(self):
        from .release_history import ReleaseHistory
        dialog = getattr(self, 'history_dialog', None)
        if dialog is None:
            self.history_dialog = dialog = ReleaseHistory(self)
        dialog.show(); dialog.raise_(); dialog.activateWindow()

    def task(self, function, callback):
        task = Task(function)
        self.tasks.append(task)
        def completed(result, error):
            self.tasks.remove(task)
            if not self.quitting:
                callback(result, error)
        task.signals.finished.connect(completed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)

    def refresh_monitors(self):
        previous = self.monitor.currentData()
        self.monitor.clear()
        if windows.IS_WINDOWS:
            try:
                monitors = windows.monitor_rectangles()
                try:
                    labels = {display.device.casefold(): display.screen.name()
                              for display in windows.map_displays(QApplication.screens(), monitors)}
                except RuntimeError:
                    # Full-monitor capture doesn't require a Qt/GDI join.
                    labels = {}
                for index, (device, rect) in enumerate(monitors):
                    label = labels.get(device.casefold()) or device
                    self.monitor.addItem(f"Monitor {index + 1} · {label}", device)
            except Exception as error:
                self.statusBar().showMessage(f"Cannot read displays: {error}")
        else:
            for index, screen in enumerate(QApplication.screens()):
                self.monitor.addItem(f"Monitor {index + 1} · {screen.name()}", screen.name())
        restored = self.monitor.findData(previous)
        if restored >= 0:
            self.monitor.setCurrentIndex(restored)

    def delay_changed(self):
        self.settings.values["delay"] = self.delay.currentData()
        try:
            self.settings.save()
        except OSError as error:
            self.error(error)

    def bring_forward(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def confirm_discard(self):
        if self.updating:
            self.statusBar().showMessage('An update is in progress. Follow the PowerShell window to finish or cancel it.', 8000)
            return False
        if not self.finish_autosaves():
            return False
        if self.export_busy or self.history_busy:
            self.statusBar().showMessage("Please wait for the current save to finish.")
            return False
        if self.doc and self.doc.dirty:
            result = QMessageBox.question(self, "Unsaved session", "Discard the current unsaved capture or edits? Use Save As or Save to History first to keep them.", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            return result == QMessageBox.StandardButton.Discard
        return True

    @staticmethod
    def configure_gallery(gallery):
        gallery.setViewMode(QListView.ViewMode.IconMode)
        gallery.setResizeMode(QListView.ResizeMode.Adjust)
        gallery.setMovement(QListView.Movement.Static)
        gallery.setIconSize(QSize(230, 140))
        gallery.setGridSize(QSize(270, 210))
        gallery.setWordWrap(True)
        gallery.setSpacing(8)

    def workspace_changed(self):
        self.library_nav.setChecked(self.stack.currentWidget() is self.home)
        self.editor_nav.setChecked(self.stack.currentWidget() is self.editor)

    def resume_editor(self):
        if self.doc:
            self.stack.setCurrentWidget(self.editor)
            self.editor.canvas.setFocus()

    def show_gallery(self):
        self.refresh_library()
        self.stack.setCurrentWidget(self.home)
        self.bring_forward()

    def set_document(self, image, history_id=None):
        if self.autosave:
            previous = self.autosave
            self.autosave = None
            previous.retire()
        self.preserve_previous_recovery()
        self.project_path = None
        doc = image if isinstance(image, Document) else Document(image)
        doc.history_id = history_id
        if not isinstance(image, Document) and history_id is None:
            doc.saved_revision = -1
        self.doc = doc
        self.editor.set_document(doc)
        self.recovery.attach(doc)
        self.editor_nav.setEnabled(True)
        self.stack.setCurrentWidget(self.editor)
        self.editor_nav.setChecked(True)
        self.autosave_changed()
        self.update_autosave_ui()
        self.bring_forward()

    def start_autosave(self, path=None):
        if not self.doc:
            return
        self.autosave = AutosaveSession(self.doc, path or capture_path(self.settings['screenshots_dir']), self.task, self)
        self.autosaves.append(self.autosave)
        self.recovery.png_path = str(self.autosave.path)
        self.recovery.schedule()
        self.autosave.state_changed.connect(self.autosave_changed)
        self.autosave.flush()

    def autosave_changed(self):
        for session in self.autosaves[:]:
            if session.retired and not session.busy and (not session.pending or session.error):
                self.autosaves.remove(session)
                session.deleteLater()
        self.update_autosave_ui()
        if self.stack.currentWidget() is self.home:
            self.refresh_screenshots()

    def update_autosave_ui(self):
        self.editor.update_state()
        session = self.autosave
        failures = [item for item in self.autosaves if item.error]
        self.save_warning.setVisible(bool(failures or self.recovery.error or self.quick_store.failures))
        if failures:
            self.save_warning_text.setText('Could not autosave. Your capture is still open. Retry, use Save As, or choose a writable Screenshots folder in Preferences.\n' + failures[-1].error)
        elif self.recovery.error:
            self.save_warning_text.setText('The PNG save and the editable recovery save are separate. Editable recovery could not be saved: ' + self.recovery.error)
        elif self.quick_store.failures:
            self.save_warning_text.setText('One or more Quick Captures are still in memory because PNG saving failed. Retry saves to keep them.')
        if session:
            text = 'Save failed · Retry with Save' if session.error else 'Saving capture…' if session.busy or session.pending else 'Saved to Screenshots'
            self.editor.save_status.setText(text)
            self.editor.save_status.setToolTip(str(session.path))
            self.editor.save_status.setIcon(icon('help' if session.error else 'save' if session.busy or session.pending else 'check', '#f7b47c' if session.error else '#a5d7bd'))
        else:
            self.editor.save_status.setText('Auto-save on for new snips' if self.settings['auto_save'] else 'Auto-save off · Save to keep')
            self.editor.save_status.setToolTip(self.settings['screenshots_dir'])
            self.editor.save_status.setIcon(icon('folder'))
        self.library_description.setText('New snips save automatically. Edit, copy or find them here.' if self.settings['auto_save'] else 'Capture, annotate and keep everything on your computer. Auto-save is off.')
        self.capture_button.setToolTip('New region · ' + self.settings['hotkey'] + '\nArrow: window, monitor and delay options')

    def retry_autosaves(self):
        self.retry_quick_captures()
        if self.recovery.error:
            self.recovery.flush()
        for session in self.autosaves[:]:
            if session.error:
                # The user may have selected a new writable directory after a failure.
                if session.written_revision is None:
                    session.path = Path(self.settings['screenshots_dir']) / session.path.name
                session.flush()

    def finish_autosaves(self):
        self.recovery.flush()
        if self.recovery.busy or (self.recovery.enabled and self.recovery.pending and not self.recovery.error):
            self.statusBar().showMessage('Finishing editable recovery. Try again in a moment.', 5000)
            return False
        for session in self.autosaves[:]:
            if session.pending and not session.error:
                session.flush()
        if any(item.busy or (item.pending and not item.error) for item in self.autosaves):
            self.statusBar().showMessage('Finishing the automatic save. Try again in a moment.', 5000)
            return False
        return True

    def quick_save(self):
        if self.autosave:
            if self.autosave.error and self.autosave.written_revision is None:
                self.autosave.path = Path(self.settings['screenshots_dir']) / self.autosave.path.name
            self.autosave.flush()
        else:
            self.start_autosave()
        self.update_autosave_ui()

    def paste_image(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            self.statusBar().showMessage('Copy an image to the clipboard first, then paste it here.', 7000)
            return
        if self.confirm_discard():
            self.set_document(image)
            if self.settings['auto_save']:
                self.start_autosave()

    def open_screenshots_folder(self):
        try:
            directory = Path(self.settings['screenshots_dir'])
            directory.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve()))):
                raise OSError('The Screenshots folder could not be opened.')
        except Exception as error:
            self.error(error)

    def refresh_library(self, *args):
        self.refresh_gallery()
        self.refresh_screenshots()

    def refresh_screenshots(self):
        if self.quitting:
            return
        if not Path(self.settings['screenshots_dir']).exists():
            self.screenshots.clear()
            self.screenshot_count.setText('Your next snip will appear here. Use New Snip or paste an image.')
            self.load_more.hide()
            return
        if self._screenshot_loading:
            self._refresh_again = True
            return
        self._screenshot_loading = True
        directory, term = Path(self.settings['screenshots_dir']), self.search.text().casefold()
        period, favourites_only, limit = self.date_filter.currentData(), self.favourites_filter.isChecked(), self.library_limit
        def load():
            if not directory.exists():
                return [], 0
            favourites = self.library_index.favourites()
            paths = []
            for path in directory.glob('*.png'):
                try:
                    modified = path.stat().st_mtime
                    if term in path.name.casefold() and date_matches(modified, period) and (not favourites_only or path_key(path) in favourites):
                        paths.append((modified, path))
                except FileNotFoundError:
                    continue
            paths.sort(key=lambda entry: entry[0], reverse=True)
            rows = []
            for modified, path in paths[:limit]:
                reader = QImageReader(str(path))
                size = reader.size()
                if not size.isValid():
                    continue
                reader.setScaledSize(size.scaled(230, 140, Qt.AspectRatioMode.KeepAspectRatio))
                thumb = reader.read()
                if not thumb.isNull():
                    label = datetime.fromtimestamp(modified).strftime('Snip · %d %b · %H:%M:%S') if path.stem.startswith('BeastSnip_') else path.stem
                    favourite = path_key(path) in favourites
                    rows.append((str(path), size.width(), size.height(), thumb, label, favourite))
            return rows, len(paths)
        def completed(result, error):
            self._screenshot_loading = False
            current = (Path(self.settings['screenshots_dir']), self.search.text().casefold(), self.date_filter.currentData(), self.favourites_filter.isChecked(), self.library_limit)
            if (directory, term, period, favourites_only, limit) != current:
                self._refresh_again = True
            elif error:
                self.screenshot_count.setText('Could not read Screenshots: ' + error)
            else:
                rows, total = result
                previous = set(self.selected_screenshots())
                self.screenshots.clear()
                for path, width, height, thumb, label, favourite in rows:
                    item = QListWidgetItem(QIcon(QPixmap.fromImage(thumb)), ('★ ' if favourite else '') + f'{label}\n{width} × {height} px')
                    item.setData(Qt.ItemDataRole.UserRole, path)
                    item.setToolTip(path + ('\nFavourite' if favourite else ''))
                    self.screenshots.addItem(item)
                    if path in previous:
                        item.setSelected(True)
                self.screenshot_count.setText((f'{total} screenshot' + ('s' if total != 1 else '') + (f' · Showing the newest {limit}' if total > limit else '')) if total else 'No matches.' if term or favourites_only or period != 'all' else 'Your next snip will appear here. Use New Snip or paste an image.')
                self.screenshot_count.setToolTip(str(directory))
                self.load_more.setVisible(total > limit)
                self.library_selection_changed()
            if self._refresh_again:
                self._refresh_again = False
                self.refresh_screenshots()
        self.task(load, completed)

    def selected_screenshot(self):
        selected = self.selected_screenshots()
        if len(selected) == 1:
            return selected[0]
        item = self.screenshots.currentItem()
        if not item:
            self.statusBar().showMessage('Select a screenshot first.', 5000)
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def open_screenshot(self):
        path = self.selected_screenshot()
        if path:
            self.open_image(path)

    def copy_screenshot(self):
        path = self.selected_screenshot()
        if path:
            image = QImage(path)
            if image.isNull():
                self.error('This screenshot is missing or could not be read. Refresh the library.')
            else:
                self.copy_to_clipboard(image)

    def show_commands(self):
        if self.updating:
            return
        has_doc = lambda: self.doc is not None
        always = lambda: True
        commands = [
            ('Capture a region · New Snip', lambda: self.capture('region'), always),
            ('Capture active window', lambda: self.capture('window'), always),
            ('Capture selected monitor', lambda: self.capture('monitor'), always),
            ('Scrolling capture · long webpages and documents', self.start_scrolling_capture, always),
            ('Toggle Quick Capture mode', lambda: self.set_quick_capture(not self.settings['quick_capture']), always),
            ('Show latest Quick Capture preview', self.show_quick_preview, always),
            ('Open Editable Project', self.open_project, always),
            ('Save Editable Project · Ctrl+Shift+P', self.save_editable_project, has_doc),
            ('Restore last editable session', self.restore_recovery, always),
            ('Update Centre · releases and rollback', self.show_update_centre, always),
            ('Version History · changelog for every update', self.show_changelog, always),
            ('Open an image · Ctrl+O', self.open_image, always),
            ('Paste image from clipboard · Ctrl+V', self.paste_image, always),
            ('Open screenshot library', self.show_gallery, always),
            ('Resume editor', self.resume_editor, has_doc),
            ('Open Screenshots folder', self.open_screenshots_folder, always),
            ('Preferences · Settings · Auto-save folder', self.open_settings, always),
            ('Keyboard shortcuts · Help', self.show_shortcuts, always),
            ('Save capture · Ctrl+S', self.quick_save, has_doc),
            ('Save As · Export PNG or JPEG', self.export_image, has_doc),
            ('Save to History', self.save_history, has_doc),
            ('Copy flattened image', self.copy_image, has_doc),
            ('Pin on Screen', self.pin_image, has_doc),
            ('Extract text · OCR whole image', self.extract_text, has_doc),
            ('Select OCR area', lambda: self.choose_tool('ocr'), has_doc),
            ('Show extracted text panel', self.show_ocr_panel, has_doc),
            ('Focus workspace', self.focus_workspace, has_doc),
        ]
        commands.extend((f'Tool: {label} · {key}', lambda t=tool: self.choose_tool(t), has_doc) for tool, label, key, tip in TOOLS)
        dialog = CommandPalette(commands, self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def choose_tool(self, tool):
        self.resume_editor()
        self.editor.canvas.set_tool(tool)

    def show_ocr_panel(self):
        self.resume_editor()
        if self.doc:
            self.editor.show_ocr(self.doc.ocr_text)

    def focus_workspace(self):
        self.resume_editor()
        self.editor.toggle_focus()

    def show_shortcuts(self):
        QMessageBox.information(self, 'BeastSnip · Keyboard shortcuts',
            'CAPTURE\n' + self.settings['hotkey'] + '  New region (global)\n\n'
            'WORKSPACE\nCtrl+K  Find any action\nCtrl+O  Open image\nCtrl+V  Paste image\n'
            'Ctrl+S  Save to Screenshots\nCtrl+Shift+P  Save Editable Project\nCtrl+Shift+S  Save As…\nCtrl+C  Copy image (or selected OCR text)\n'
            'Ctrl+Z / Ctrl+Y  Undo / Redo\nCtrl+Shift+F  Focus workspace\nF5  Refresh library\n\n'
            'TOOLS\nV Select · H Pan · P Pen · I Highlight · A Arrow\nB Box · F Fill · O Ellipse · T Text · N Step\n'
            'G Brush · L Line · U Rounded Box · E Annotation Eraser\n'
            'R Redact · C Crop · Esc Select\n\nShift: equal-sided shapes / 45-degree lines\n'
            'Colour: palette and hex values · Style: opacity, pattern, fill and smoothing\n'
            'Ctrl+wheel to zoom · Middle mouse to pan\nDouble-click a text annotation to edit it.')

    def show_about(self):
        QMessageBox.about(self, 'About BeastSnip', f'BeastSnip {__version__}\nCapture. Clarify. Keep.\n\nNative Windows screenshots, annotations and offline OCR.\nYour images stay on your computer.\n\nNew captures: ' + self.settings['screenshots_dir'])

    def capture(self, mode):
        if self.updating:
            return
        if QApplication.activeModalWidget() is not None:
            self.statusBar().showMessage("Close the open dialog before capturing.", 7000)
            return
        if self.capture_busy or (not self.settings["quick_capture"] and not self.confirm_discard()):
            return
        try:
            windows.require_windows()
        except RuntimeError as error:
            self.error(error)
            return
        self.integration.track_foreground()
        self.editor.colour_palette.hide()
        self.editor.style_popup.hide()
        self.capture_mode = mode
        self.capture_quick = self.settings["quick_capture"]
        self.capture_hwnd = self.integration.last_external
        self.capture_monitor = self.monitor.currentData()
        self.capture_busy = True
        self.was_visible = self.isVisible()
        owned = list(self.pins) + ([self.quick_preview] if self.quick_preview else [])
        self.hidden_pins = [pin for pin in owned if pin.isVisible()]
        for pin in self.hidden_pins:
            pin.hide()
        self.hide()
        # Let DWM remove our windows before freezing desktop pixels.
        self.capture_timer.start(self.settings["delay"] * 1000 + 220)

    def perform_capture(self):
        try:
            if self.capture_mode in ("region", "scroll"):
                self.capture_session = RegionSession(self, magnifier=self.settings["magnifier"])
                self.capture_session.captured.connect(self.scrolling_region_selected if self.capture_mode == "scroll" else self.captured)
                self.capture_session.cancelled.connect(self.capture_cancelled)
                self.capture_session.show()
                return
            if self.capture_mode == "window":
                rect = windows.window_rectangle(self.capture_hwnd)
            else:
                monitors = {device.casefold(): rect for device, rect in windows.monitor_rectangles()}
                key = (self.capture_monitor or "").casefold()
                if key not in monitors:
                    self.refresh_monitors()
                    raise RuntimeError("The display layout changed during the capture delay. The monitor list has been refreshed; select a monitor and retry.")
                rect = monitors[key]
            self.captured(windows.grab_pixels(rect))
        except Exception as error:
            self.capture_cancelled()
            self.bring_forward()
            self.error(error)

    def restore_pins(self):
        for pin in getattr(self, "hidden_pins", []):
            if pin in self.pins or pin is self.quick_preview:
                pin.show()
        self.hidden_pins = []

    def capture_cancelled(self):
        self.capture_busy = False
        if self.scroll_controller:
            self.scroll_controller.cleanup()
            self.scroll_controller.deleteLater()
            self.scroll_controller = None
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None
        self.restore_pins()
        if getattr(self, "was_visible", False):
            self.bring_forward()
        self.statusBar().showMessage("Capture cancelled.")

    def captured(self, image):
        self.capture_busy = False
        if self.scroll_controller:
            self.scroll_controller.cleanup()
            self.scroll_controller.deleteLater()
            self.scroll_controller = None
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None
        self.restore_pins()
        if getattr(self, "capture_quick", self.settings["quick_capture"]):
            self.captured_quickly(image)
            return
        self.set_document(image)
        self.statusBar().showMessage("Captured · Choose a tool on the left, or press Ctrl+K to find an action.")
        if self.settings["auto_save"]:
            self.start_autosave()
        if self.settings["auto_copy"]:
            self.copy_image()
        if self.settings["auto_history"]:
            self.save_history()

    def open_image(self, path=None):
        if isinstance(path, (str, Path)) and str(path).lower().endswith(".beastsnip"):
            self.open_project(path)
            return
        if not self.confirm_discard():
            return
        if not isinstance(path, (str, Path)):
            path = QFileDialog.getOpenFileName(self, "Open image", self.settings["save_dir"], "Images and projects (*.png *.jpg *.jpeg *.bmp *.webp *.beastsnip)")[0]
        if not path:
            return
        if str(path).lower().endswith(".beastsnip"):
            self.load_project_into_editor(path)
            return
        try:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                raise ValueError("The image could not be opened. " + reader.errorString())
            self.set_document(image)
            if self.settings["auto_save"] and Path(path).suffix.lower() == ".png" and Path(path).resolve().parent == Path(self.settings["screenshots_dir"]).resolve():
                self.start_autosave(path)
        except Exception as error:
            self.error(error)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".beastsnip") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".beastsnip"):
                self.open_image(url.toLocalFile())
                event.acceptProposedAction()
                break

    def copy_image(self):
        if not self.doc:
            return
        self.copy_to_clipboard(self.doc.flatten())

    def copy_to_clipboard(self, image):
        try:
            clipboard = QApplication.clipboard()
            clipboard.setImage(image)
            copied = clipboard.image()
            if copied.isNull() or copied.size() != image.size():
                raise RuntimeError("The clipboard is busy. Close other clipboard tools and try again.")
            self.statusBar().showMessage("Flattened image copied. Earlier clipboard copies are not erased.", 9000)
        except Exception as error:
            self.error(error)

    def export_image(self):
        if not self.doc or self.export_busy:
            return
        default = Path(self.settings["save_dir"]) / datetime.now().strftime("BeastSnip_%Y-%m-%d_%H-%M-%S.png")
        path, selected = QFileDialog.getSaveFileName(self, "Save flattened image", str(default), "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path:
            return
        if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg"):
            path += ".jpg" if selected.startswith("JPEG") else ".png"
            if Path(path).exists() and QMessageBox.question(self, "Replace image?", f"Replace the existing file {path}?") != QMessageBox.StandardButton.Yes:
                return
        if self.autosave and Path(path).resolve() == self.autosave.path.resolve():
            # Keep writes to this PNG in the same serial queue as automatic edits.
            self.autosave.pending = True
            self.autosave.flush()
            return
        doc, revision, image = self.doc, self.doc.revision, self.doc.flatten()
        quality = self.settings["jpeg_quality"]
        self.export_busy = True
        self.statusBar().showMessage("Saving flattened image…")
        def completed(result, error):
            self.export_busy = False
            if error:
                self.error(error)
                return
            if self.doc is doc and doc.revision == revision:
                doc.mark_saved()
            self.statusBar().showMessage(f"Saved flattened image: {path}", 12000)
        self.task(lambda: save_image(path, image, quality), completed)

    def save_history(self):
        if not self.doc or self.history_busy:
            return
        doc, revision, image = self.doc, self.doc.revision, self.doc.flatten()
        item_id, directory = doc.history_id, str(self.history.directory)
        text = doc.ocr_text
        self.history_busy = True
        self.statusBar().showMessage("Saving flattened image and thumbnail to history…")
        def store():
            history = History(directory)
            try:
                return history.save(image, item_id, ocr=text)
            finally:
                history.close()
        def completed(result, error):
            self.history_busy = False
            if error:
                self.error(error)
                return
            if self.doc is doc:
                doc.history_id = result
                if doc.revision == revision:
                    # Preserve any OCR text edited while the worker was saving.
                    doc.saved_revision = revision
                    doc.saved_ocr_text = text
                    doc.changed.emit()
            self.refresh_gallery()
            self.statusBar().showMessage("History saved with flattened pixels. Saving again updates this item.", 10000)
        self.task(store, completed)

    def extract_text(self, area=None):
        if not self.doc or self.ocr_job:
            return
        try:
            executable = find_tesseract(self.settings["ocr_path"])
        except RuntimeError as error:
            self.error(error)
            return
        image = self.doc.flatten()
        if area is not None:
            image = image.copy(area.toAlignedRect().intersected(image.rect()))
        self.ocr_generation = self.doc, self.doc.revision
        self.ocr_job = OCRJob(image, executable, self.settings["ocr_language"], self.settings["ocr_data_dir"])
        self.ocr_job.signals.finished.connect(self.ocr_complete, Qt.ConnectionType.QueuedConnection)
        self.editor.ocr_button.setEnabled(False)
        self.editor.ocr_area_button.setEnabled(False)
        self.statusBar().showMessage("Extracting text locally…")
        QThreadPool.globalInstance().start(self.ocr_job)

    def ocr_complete(self, text, error):
        self.ocr_job = None
        self.editor.ocr_button.setEnabled(True)
        self.editor.ocr_area_button.setEnabled(True)
        if error:
            self.error(error)
            return
        if (self.doc, self.doc.revision if self.doc else None) != self.ocr_generation:
            self.statusBar().showMessage("The image changed during OCR; extract again to use the current pixels.")
            return
        self.doc.ocr_text = text
        self.editor.show_ocr(text)
        self.statusBar().showMessage("Text extracted locally. Save to History to store it." if text else "OCR finished; no readable text was found.", 12000)

    def pin_image(self):
        if self.doc:
            pin = PinnedWindow(self.doc.flatten())
            self.pins.append(pin)
            pin.destroyed.connect(lambda: self.pins.remove(pin) if pin in self.pins else None)
            pin.show()

    def refresh_gallery(self):
        try:
            rows = self.history.search(self.search.text() if hasattr(self, "search") else "")
            self.gallery.clear()
            for row in rows:
                pixmap = QPixmap()
                pixmap.loadFromData(row["thumbnail"], "PNG")
                timestamp = datetime.fromisoformat(row["created"]).astimezone().strftime("%d %b %Y %H:%M")
                item = QListWidgetItem(QIcon(pixmap), f"{row['title']}\n{row['width']} × {row['height']} px · {timestamp}\n{row['tags']}")
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setToolTip(row["title"] + "\n" + row["tags"])
                self.gallery.addItem(item)
            self.empty.setVisible(not rows)
            self.gallery.setVisible(bool(rows))
        except Exception as error:
            self.error(error)

    def selected_history(self):
        item = self.gallery.currentItem()
        if not item:
            self.statusBar().showMessage("Select a screenshot in the gallery first.", 5000)
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def open_history(self):
        item_id = self.selected_history()
        if not item_id or not self.confirm_discard():
            return
        try:
            self.set_document(self.history.image(item_id), item_id)
            row = self.history.db.execute("SELECT ocr FROM captures WHERE id=?", (item_id,)).fetchone()
            if row and row["ocr"]:
                self.doc.ocr_text = row["ocr"]
                self.doc.saved_ocr_text = row["ocr"]
                self.editor.show_ocr(row["ocr"])
        except Exception as error:
            self.error(error)

    def copy_history(self):
        item_id = self.selected_history()
        if item_id:
            try:
                self.copy_to_clipboard(self.history.image(item_id))
            except Exception as error:
                self.error(error)

    def rename_history(self):
        item_id = self.selected_history()
        if not item_id:
            return
        try:
            row = self.history.db.execute("SELECT title,tags FROM captures WHERE id=?", (item_id,)).fetchone()
            title, ok = QInputDialog.getText(self, "History title", "Title", text=row["title"])
            if not ok:
                return
            tags, ok = QInputDialog.getText(self, "History tags", "Tags (comma separated)", text=row["tags"])
            if not ok:
                return
            self.history.rename(item_id, title.strip() or "Untitled capture", tags)
            self.refresh_gallery()
        except Exception as error:
            self.error(error)

    def history_folder(self):
        item_id = self.selected_history()
        if item_id:
            directory = str(self.history.directory)
            def materialize():
                history = History(directory)
                try:
                    return str(history.materialize(item_id))
                finally:
                    history.close()
            def completed(result, error):
                if error:
                    self.error(error)
                elif not QDesktopServices.openUrl(QUrl.fromLocalFile(directory)):
                    self.error("The containing folder could not be opened.")
                else:
                    self.statusBar().showMessage("Opened the folder for this saved image.")
            self.task(materialize, completed)

    def delete_history(self):
        item_id = self.selected_history()
        if item_id and QMessageBox.question(self, "Delete screenshot", "Remove this image, title, tags and OCR from Saved History? Screenshots folder files, separate exports and clipboard copies remain.") == QMessageBox.StandardButton.Yes:
            try:
                self.history.delete(item_id)
                if self.doc and self.doc.history_id == item_id:
                    self.doc.history_id = None
                    self.doc.saved_revision = -1
                self.refresh_gallery()
            except Exception as error:
                self.error(error)

    def clear_history(self):
        if self.history_busy:
            return
        if QMessageBox.question(self, "Clear history", "Permanently remove all images, titles, tags and OCR from Saved History? Screenshots folder files, separate exports and clipboard copies remain.") == QMessageBox.StandardButton.Yes:
            try:
                self.history.clear()
                if self.doc and self.doc.history_id:
                    self.doc.history_id = None
                    self.doc.saved_revision = -1
                self.refresh_gallery()
            except Exception as error:
                self.error(error)

    def open_settings(self):
        if self.updating:
            return
        self.bring_forward()
        if self.history_busy or self.recovery.busy:
            self.statusBar().showMessage("Wait for the current save to finish before changing settings.")
            return
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old = self.settings.values.copy()
        replacement = None
        try:
            values = dialog.values()
            replacement = History(values["history_dir"])
            self.settings.values = values
            self.settings.save()
            self.history.close()
            self.history = replacement
            if old["history_dir"] != values["history_dir"] and self.doc:
                self.doc.history_id = None
            warning = self.integration.register(values["hotkey"])
            self.recovery.enabled = values["recover_session"] and not self.smoke
            if not values["recover_session"]:
                self.clear_recovery(confirm=False)
            elif self.recovery.enabled:
                self.recovery.schedule()
            self.sync_capture_preferences()
            self.refresh_library()
            self.update_autosave_ui()
            self.statusBar().showMessage(warning or "Settings saved. New captures use these preferences.", 15000)
            if warning:
                self.error(warning)
        except Exception as error:
            if replacement is not None and replacement is not self.history:
                replacement.close()
            self.settings.values = old
            self.error(error)

    def closeEvent(self, event):
        if not self.quitting and self.settings["close_to_tray"] and self.tray.isVisible():
            if not self.settings["close_explained"]:
                QMessageBox.information(self, "BeastSnip stays in the tray", "Closing hides BeastSnip in the system tray and keeps your editing session in memory. Use the tray's Quit BeastSnip action to exit. You can change this in Settings.")
                self.settings.values["close_explained"] = True
                try:
                    self.settings.save()
                except OSError:
                    logging.warning("Could not persist tray explanation")
            self.hide()
            event.ignore()
            return
        if not self.quitting:
            event.ignore()
            self.quit_app()
        else:
            event.accept()

    def quit_app(self):
        if self.quick_store.failures and not self.smoke:
            choice = QMessageBox.question(self, "Unstored Quick Captures", "Some Quick Captures have not been saved. Discard them and quit? Choose No to retry saving first.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if choice != QMessageBox.StandardButton.Yes:
                self.retry_quick_captures()
                return
        if self.smoke:
            self.shutdown()
            return
        if not self.finish_autosaves():
            return
        if self.ocr_job or self.tasks:
            self.statusBar().showMessage("Please wait for background saving or OCR to finish before quitting (OCR timeout: 90 seconds).")
            self.bring_forward()
            return
        if not self.confirm_discard():
            self.bring_forward()
            return
        self.shutdown()

    def shutdown(self):
        if self.quitting:
            return
        self.quitting = True
        self.capture_timer.stop()
        self.recovery.timer.stop()
        if self.quick_preview:
            self.quick_preview.close()
        if self.scroll_controller:
            self.scroll_controller.cleanup()
        if self.update_dialog:
            self.update_dialog.poll_timer.stop()
            self.update_dialog.close()
        if self.capture_session:
            self.capture_session.cleanup()
        self.integration.close()
        self.tray.hide()
        for pin in list(self.pins):
            pin.close()
        self.history.close()
        self.close()
        QApplication.instance().quit()


def main():
    import argparse
    from logging.handlers import RotatingFileHandler
    parser = argparse.ArgumentParser(description="BeastSnip native screenshot editor")
    parser.add_argument("--smoke-test", action="store_true", help="Start the real UI briefly without tray or hotkey registration")
    args = parser.parse_args()
    windows.enable_dpi_awareness()
    identity_failed = False
    try:
        windows.set_app_identity()
    except OSError:
        identity_failed = True
    app = QApplication(sys.argv)
    app.setApplicationName("BeastSnip")
    app.setOrganizationName("BeastSnip")
    app.setWindowIcon(QIcon(str(resource('beastsnip.ico'))))
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    data_dir().mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir() / "beastsnip.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    if identity_failed:
        logging.warning('The Windows application identity could not be set.')
    def exception_handler(kind, value, trace):
        # Do not log exception messages/locals: they may contain screenshot text.
        logging.error("Unhandled UI exception (%s)", kind.__name__)
        if args.smoke_test:
            print("Startup smoke test failed: " + kind.__name__, file=sys.stderr)
            app.exit(1)
            return
        QMessageBox.critical(None, "BeastSnip", "An operation failed. Please retry or restart BeastSnip. Error type: " + kind.__name__)
    sys.excepthook = exception_handler
    instance = SingleInstance(app) if not args.smoke_test else None
    try:
        if args.smoke_test and identity_failed:
            raise RuntimeError('Windows could not assign the BeastSnip taskbar identity.')
        if instance and not instance.acquire():
            return 0
        window = MainWindow(smoke=args.smoke_test)
        if instance:
            instance.activated.connect(window.bring_forward)
        window.show()
        if args.smoke_test:
            if app.windowIcon().pixmap(32, 32).isNull() or window.windowIcon().pixmap(32, 32).isNull():
                raise RuntimeError('The BeastSnip application icon could not be loaded.')
            # Exercise actual editing, flattening, UI construction and event loop.
            from PySide6.QtCore import QPointF, QRectF
            from .document import Annotation
            image = QImage(640, 360, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            window.set_document(image)
            window.doc.add(Annotation("redact", [QPointF(10, 10), QPointF(70, 60)]))
            window.doc.crop(QRectF(0, 0, 320, 180))
            window.doc.undo()
            window.doc.redo()
            assert window.doc.flatten().size() == QSize(320, 180)
            QTimer.singleShot(650, window.shutdown)
        code = app.exec()
        if instance:
            instance.close()
        return code
    except Exception as error:
        logging.error("Startup failed (%s)", type(error).__name__)
        if args.smoke_test:
            raise
        QMessageBox.critical(None, "BeastSnip could not start", str(error))
        return 1
