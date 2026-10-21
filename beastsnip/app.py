from datetime import datetime
import logging
from pathlib import Path
import sys

from PySide6.QtCore import (QDir, QEvent, QLockFile, QObject, QSize, Qt, QThreadPool,
    QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QImage, QImageReader, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget, QLineEdit)

from .capture import RegionSession
from .config import Settings, data_dir, resource
from .dialogs import PinnedWindow, SettingsDialog
from .document import Document, save_image
from .editor import Editor
from .ocr import OCRJob, find_tesseract
from .storage import History
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


class MainWindow(QMainWindow):
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
        self.setWindowTitle(f"BeastSnip {__version__}")
        self.setWindowIcon(QIcon(str(resource("beastsnip.ico"))))
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 10)
        nav = QHBoxLayout()
        title = QLabel("BeastSnip")
        title.setObjectName("hero")
        nav.addWidget(title)
        self.add_button(nav, "Gallery", self.show_gallery)
        capture = self.add_button(nav, "New Region", lambda: self.capture("region"))
        capture.setObjectName("primary")
        self.add_button(nav, "Active Window", lambda: self.capture("window"))
        self.monitor = QComboBox()
        self.refresh_monitors()
        self.monitor.setToolTip("Choose the monitor to capture")
        nav.addWidget(self.monitor)
        self.add_button(nav, "Capture Monitor", lambda: self.capture("monitor"))
        self.delay = QComboBox()
        for delay in (0, 3, 5, 10):
            self.delay.addItem("No delay" if delay == 0 else f"{delay}s delay", delay)
        self.delay.setCurrentIndex((0, 3, 5, 10).index(self.settings["delay"]))
        self.delay.currentIndexChanged.connect(self.delay_changed)
        nav.addWidget(self.delay)
        nav.addStretch()
        self.add_button(nav, "Open…", self.open_image)
        self.add_button(nav, "Settings", self.open_settings)
        root.addLayout(nav)
        self.stack = QStackedWidget()
        self.home = QWidget()
        home_layout = QVBoxLayout(self.home)
        heading = QLabel("Your screenshots, kept on your computer")
        heading.setStyleSheet("font-size:19px; font-weight:600; padding-top:12px")
        home_layout.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles, tags and explicitly saved OCR text…")
        self.search.textChanged.connect(self.refresh_gallery)
        home_layout.addWidget(self.search)
        self.empty = QLabel("Capture a region or open an image to get started.\nHistory is saved only when you choose Save to History, unless enabled in Settings.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("font-size:16px; color:#bdb8d1; padding:30px;")
        home_layout.addWidget(self.empty, 1)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setMovement(QListView.Movement.Static)
        self.gallery.setIconSize(QSize(250, 150))
        self.gallery.setGridSize(QSize(300, 245))
        self.gallery.setWordWrap(True)
        self.gallery.itemDoubleClicked.connect(lambda item: self.open_history())
        home_layout.addWidget(self.gallery, 1)
        gallery_actions = QHBoxLayout()
        for label, callback in [("Open in Editor", self.open_history), ("Copy Image", self.copy_history),
                                ("Edit Title / Tags", self.rename_history), ("Open Folder", self.history_folder),
                                ("Delete", self.delete_history), ("Clear History", self.clear_history)]:
            self.add_button(gallery_actions, label, callback)
        gallery_actions.addStretch()
        home_layout.addLayout(gallery_actions)
        self.stack.addWidget(self.home)
        self.editor = Editor()
        self.editor.copy_requested.connect(self.copy_image)
        self.editor.save_requested.connect(self.export_image)
        self.editor.history_requested.connect(self.save_history)
        self.editor.pin_requested.connect(self.pin_image)
        self.editor.ocr_requested.connect(self.extract_text)
        self.stack.addWidget(self.editor)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("BeastSnip · local screenshots")
        menu = QMenu(self)
        for label, callback in [("New region capture", lambda: self.capture("region")),
                                ("Capture active window", lambda: self.capture("window")),
                                ("Capture selected monitor", lambda: self.capture("monitor")),
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
        self.refresh_gallery()
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

    def task(self, function, callback):
        task = Task(function)
        self.tasks.append(task)
        def completed(result, error):
            self.tasks.remove(task)
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
        if self.export_busy or self.history_busy:
            self.statusBar().showMessage("Please wait for the current save to finish.")
            return False
        if self.doc and self.doc.dirty:
            result = QMessageBox.question(self, "Unsaved session", "Discard the current unsaved capture or edits? Use Save As or Save to History first to keep them.", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            return result == QMessageBox.StandardButton.Discard
        return True

    def show_gallery(self):
        self.refresh_gallery()
        self.stack.setCurrentWidget(self.home)
        self.bring_forward()
        if self.doc:
            self.statusBar().showMessage("Current editing session is kept in memory. Use Open in Editor or capture to replace it.")
            # Give users a visible path back to their retained editing session.
            if not hasattr(self, "resume_action"):
                self.resume_action = QPushButton("Resume Editor")
                self.resume_action.clicked.connect(lambda: self.stack.setCurrentWidget(self.editor))
                self.home.layout().insertWidget(1, self.resume_action)
            self.resume_action.show()

    def set_document(self, image, history_id=None):
        doc = Document(image)
        doc.history_id = history_id
        if history_id is None:
            doc.saved_revision = -1  # New capture/import must be explicitly kept.
        self.doc = doc
        self.editor.set_document(doc)
        self.stack.setCurrentWidget(self.editor)
        self.bring_forward()

    def capture(self, mode):
        if QApplication.activeModalWidget() is not None:
            self.statusBar().showMessage("Close the open dialog before capturing.", 7000)
            return
        if self.capture_busy or not self.confirm_discard():
            return
        try:
            windows.require_windows()
        except RuntimeError as error:
            self.error(error)
            return
        self.integration.track_foreground()
        self.capture_mode = mode
        self.capture_hwnd = self.integration.last_external
        self.capture_monitor = self.monitor.currentData()
        self.capture_busy = True
        self.was_visible = self.isVisible()
        self.hidden_pins = [pin for pin in self.pins if pin.isVisible()]
        for pin in self.hidden_pins:
            pin.hide()
        self.hide()
        # Let DWM remove our windows before freezing desktop pixels.
        self.capture_timer.start(self.settings["delay"] * 1000 + 220)

    def perform_capture(self):
        try:
            if self.capture_mode == "region":
                self.capture_session = RegionSession(self)
                self.capture_session.captured.connect(self.captured)
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
            if pin in self.pins:
                pin.show()
        self.hidden_pins = []

    def capture_cancelled(self):
        self.capture_busy = False
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None
        self.restore_pins()
        if getattr(self, "was_visible", False):
            self.bring_forward()
        self.statusBar().showMessage("Capture cancelled.")

    def captured(self, image):
        self.capture_busy = False
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None
        self.restore_pins()
        self.set_document(image)
        self.statusBar().showMessage("Captured · Edit in memory, then save or copy a flattened image.")
        if self.settings["auto_copy"]:
            self.copy_image()
        if self.settings["auto_history"]:
            self.save_history()

    def open_image(self, path=None):
        if not self.confirm_discard():
            return
        if not isinstance(path, (str, Path)):
            path = QFileDialog.getOpenFileName(self, "Open image", self.settings["save_dir"], "Images (*.png *.jpg *.jpeg *.bmp *.webp)")[0]
        if not path:
            return
        try:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                raise ValueError("The image could not be opened. " + reader.errorString())
            self.set_document(image)
        except Exception as error:
            self.error(error)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
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
                    self.statusBar().showMessage("Opened history folder. The PNG is a flattened convenience copy; the gallery uses SQLite.")
            self.task(materialize, completed)

    def delete_history(self):
        item_id = self.selected_history()
        if item_id and QMessageBox.question(self, "Delete screenshot", "Remove this flattened image, thumbnail, title, tags and OCR from history? Separately exported files and clipboard copies remain.") == QMessageBox.StandardButton.Yes:
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
        if QMessageBox.question(self, "Clear history", "Permanently remove all gallery images, thumbnails, titles, tags and saved OCR? Separately exported files and clipboard copies remain.") == QMessageBox.StandardButton.Yes:
            try:
                self.history.clear()
                if self.doc and self.doc.history_id:
                    self.doc.history_id = None
                    self.doc.saved_revision = -1
                self.refresh_gallery()
            except Exception as error:
                self.error(error)

    def open_settings(self):
        self.bring_forward()
        if self.history_busy:
            self.statusBar().showMessage("Wait for history saving to finish before changing settings.")
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
            self.refresh_gallery()
            self.statusBar().showMessage(warning or "Settings saved.", 15000)
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
        if self.smoke:
            self.shutdown()
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
    app = QApplication(sys.argv)
    app.setApplicationName("BeastSnip")
    app.setOrganizationName("BeastSnip")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    data_dir().mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir() / "beastsnip.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
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
        if instance and not instance.acquire():
            return 0
        window = MainWindow(smoke=args.smoke_test)
        if instance:
            instance.activated.connect(window.bring_forward)
        window.show()
        if args.smoke_test:
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
