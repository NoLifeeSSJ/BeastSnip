"""Non-activating capture previews and independent background PNG saves."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .autosave import capture_path
from .document import save_image


@dataclass
class QuickItem:
    image: QImage
    path: Path
    busy: bool = False
    error: str = ''
    saved: bool = False


class QuickCaptureStore(QObject):
    changed = Signal(object)

    def __init__(self, submit, parent=None):
        super().__init__(parent)
        self.submit, self.items = submit, []

    def capture(self, image, directory):
        item = QuickItem(QImage(image), capture_path(directory))
        self.items.append(item)
        self.save(item)
        return item

    def save(self, item, directory=None):
        if item.busy:
            return
        if directory is not None and not item.saved:
            item.path = Path(directory) / item.path.name
        item.busy, item.error = True, ''
        self.changed.emit(item)
        def completed(result, error):
            item.busy, item.error, item.saved = False, error, not bool(error)
            # Retain failed captures until retried or explicitly discarded.
            successful = [old for old in self.items if old.saved and not old.busy]
            for old in successful[:-3]:
                self.items.remove(old)
            self.changed.emit(item)
        self.submit(lambda: save_image(item.path, item.image), completed)

    @property
    def failures(self):
        return [item for item in self.items if item.error]


class QuickPreview(QWidget):
    open_requested = Signal(object)
    copy_requested = Signal(object)
    pin_requested = Signal(object)
    retry_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('BeastSnip · Capture preview')
        self.setObjectName('quickPreview')
        self.setFixedWidth(348)
        self.item = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        heading = QHBoxLayout()
        self.status = QLabel('Saving snip…')
        self.status.setObjectName('toolName')
        heading.addWidget(self.status, 1)
        close = QPushButton('×')
        close.setAccessibleName('Dismiss capture preview')
        close.setFixedWidth(30)
        close.clicked.connect(self.hide)
        heading.addWidget(close)
        layout.addLayout(heading)
        self.thumbnail = QLabel()
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setFixedHeight(130)
        layout.addWidget(self.thumbnail)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setObjectName('muted')
        layout.addWidget(self.detail)
        actions = QHBoxLayout()
        self.open_button = QPushButton('Open')
        self.open_button.clicked.connect(lambda: self.open_requested.emit(self.item))
        actions.addWidget(self.open_button)
        for name, signal in [('Copy', self.copy_requested), ('Pin', self.pin_requested), ('Retry', self.retry_requested)]:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, s=signal: s.emit(self.item))
            actions.addWidget(button)
            if name == 'Retry':
                self.retry_button = button
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def display(self, item):
        self.item = item
        self.thumbnail.setPixmap(QPixmap.fromImage(item.image).scaled(316, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.status.setText('Could not save snip' if item.error else 'Saving snip…' if item.busy else 'Snip saved')
        self.detail.setText(item.error or f'{item.image.width()} × {item.image.height()} px · Quick Capture')
        self.detail.setToolTip(str(item.path))
        self.open_button.setEnabled(item.saved)
        self.retry_button.setVisible(bool(item.error))
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        self.move(available.right() - self.width() - 18, available.bottom() - self.height() - 18)
        self.show()
        if item.error or item.busy:
            self.timer.stop()
        else:
            self.timer.start(8000)

    def enterEvent(self, event):
        self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.item and self.item.saved:
            self.timer.start(8000)
        super().leaveEvent(event)
