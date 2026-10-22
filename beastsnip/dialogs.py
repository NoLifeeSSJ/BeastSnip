from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget, QSizePolicy, QScrollArea)

from .windows import parse_hotkey


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BeastSnip settings")
        self.setMinimumWidth(620)
        self.resize(680, 580)
        self.settings, self.fields = settings, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        heading = QLabel('Make BeastSnip yours')
        heading.setObjectName('sectionTitle')
        layout.addWidget(heading)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        forms = {}
        for name in ('Captures & storage', 'Workspace', 'Offline OCR'):
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(16, 20, 16, 16)
            form.setSpacing(14)
            forms[name] = form
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tabs.addTab(scroll, name)
        for key, title, folder, tab in [
            ('screenshots_dir', 'Screenshots folder', True, 'Captures & storage'),
            ('save_dir', 'Save As default folder', True, 'Captures & storage'),
            ('history_dir', 'Saved History folder', True, 'Captures & storage'),
            ('ocr_path', 'Tesseract executable', False, 'Offline OCR'),
            ('ocr_data_dir', 'Language files folder', True, 'Offline OCR'),
        ]:
            row = QHBoxLayout()
            field = QLineEdit(settings[key])
            self.fields[key] = field
            row.addWidget(field)
            browse = QPushButton('Browse…')
            def choose(checked=False, field=field, folder=folder):
                path = QFileDialog.getExistingDirectory(self, 'Choose folder', field.text()) if folder else QFileDialog.getOpenFileName(self, 'Tesseract executable', field.text(), 'Executable (*.exe);;All files (*)')[0]
                if path:
                    field.setText(path)
            browse.clicked.connect(choose)
            row.addWidget(browse)
            forms[tab].addRow(title, row)
        for key, title, tab in [('hotkey', 'Global region shortcut', 'Workspace'), ('ocr_language', 'OCR language(s)', 'Offline OCR')]:
            field = QLineEdit(settings[key])
            self.fields[key] = field
            forms[tab].addRow(title, field)
        quality = QSpinBox()
        quality.setRange(1, 100)
        quality.setValue(settings['jpeg_quality'])
        self.fields['jpeg_quality'] = quality
        forms['Workspace'].addRow('JPEG quality', quality)
        for key, title, tab in [
            ('auto_save', 'Automatically save new captures and pasted images', 'Captures & storage'),
            ('auto_history', 'Also add new captures to Saved History', 'Captures & storage'),
            ('recover_session', 'Recover editable sessions after restart', 'Captures & storage'),
            ('quick_capture', 'Quick Capture: save PNGs without opening the editor', 'Workspace'),
            ('magnifier', 'Show the pixel magnifier during region selection', 'Workspace'),
            ('auto_copy', 'Copy new captures to the clipboard', 'Workspace'),
            ('close_to_tray', 'Keep running in the tray when I close the window', 'Workspace')]:
            field = QCheckBox(title)
            field.setChecked(settings[key])
            self.fields[key] = field
            forms[tab].addRow(field)
        notes = {
            'Captures & storage': 'A new capture is saved as a PNG before editing. Later image edits update that same PNG automatically. Separate exports, history items and earlier clipboard copies remain independent.\n\nFolder and auto-save preferences apply to new captures. Captures already open continue saving to their existing file. History retains searchable text only when you save it there.\n\nEditable recovery and .beastsnip projects retain the original image and annotations, including pixels under redactions. Share flattened PNGs when originals should not be included. Turning recovery off clears automatic recovery files; explicit projects remain.',
            'Workspace': 'Ctrl+K finds any action. F1 shows keyboard shortcuts. Tool controls appear only when relevant. JPEG exports use a white background. Quick Capture always saves its PNGs and keeps the current editor session. The preview offers Open, Copy and Pin. Use Scrolling Capture for long content and M to toggle the magnifier during selection.',
            'Offline OCR': 'OCR runs on this computer. English uses eng; multiple languages use codes such as eng+deu. Leave paths empty for automatic discovery. Use Repair-OCR.ps1 if the runtime or a language is missing.'
        }
        for tab, text in notes.items():
            note = QLabel(text)
            note.setWordWrap(True)
            note.setObjectName('muted')
            forms[tab].addRow(note)
        self.error = QLabel()
        self.error.setStyleSheet("color:#ffb0b8")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        result = self.settings.values.copy()
        for key, widget in self.fields.items():
            result[key] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value() if isinstance(widget, QSpinBox) else widget.text().strip()
        return result

    def validate(self):
        try:
            values = self.values()
            parse_hotkey(values["hotkey"])
            if not values["save_dir"] or not values["history_dir"] or not values["screenshots_dir"]:
                raise ValueError("Choose Screenshots, export and history folders.")
            if not values["ocr_language"]:
                raise ValueError("Choose an OCR language, for example eng.")
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class PinnedWindow(QWidget):
    def __init__(self, image):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.image = QImage(image)
        self.setWindowTitle("BeastSnip · Pinned screenshot")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(180, 130)
        self.drag_point = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        top = QHBoxLayout()
        top.addWidget(QLabel("Pinned · drag image to move"))
        top.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        top.addWidget(close)
        layout.addLayout(top)
        self.image_label = QLabel()
        self.image_label.setMinimumSize(1, 1)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.installEventFilter(self)
        layout.addWidget(self.image_label, 1)
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(20, 100)
        opacity.setValue(100)
        opacity.setToolTip("Window opacity")
        opacity.valueChanged.connect(lambda n: self.setWindowOpacity(n / 100))
        layout.addWidget(opacity)
        width = min(780, max(240, image.width()))
        self.resize(width, min(720, max(180, round(width * image.height() / image.width()) + 85)))

    def resizeEvent(self, event):
        from PySide6.QtGui import QPixmap
        super().resizeEvent(event)
        self.image_label.setPixmap(QPixmap.fromImage(self.image).scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.drag_point = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            return True
        if event.type() == QEvent.Type.MouseMove and self.drag_point is not None:
            self.move(event.globalPosition().toPoint() - self.drag_point)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self.drag_point = None
            return True
        return super().eventFilter(watched, event)
