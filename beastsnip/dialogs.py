from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget, QSizePolicy)

from .windows import parse_hotkey


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BeastSnip settings")
        self.setMinimumWidth(580)
        self.settings, self.fields = settings, {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for key, title, folder in [
            ("save_dir", "Default export folder", True), ("history_dir", "History folder", True),
            ("ocr_path", "Tesseract executable (optional)", False),
            ("ocr_data_dir", "OCR language folder (optional)", True),
        ]:
            row = QHBoxLayout()
            field = QLineEdit(settings[key])
            self.fields[key] = field
            row.addWidget(field)
            browse = QPushButton("Browse…")
            def choose(checked=False, field=field, folder=folder):
                path = QFileDialog.getExistingDirectory(self, "Choose folder", field.text()) if folder else QFileDialog.getOpenFileName(self, "Tesseract executable", field.text(), "Executable (*.exe);;All files (*)")[0]
                if path:
                    field.setText(path)
            browse.clicked.connect(choose)
            row.addWidget(browse)
            form.addRow(title, row)
        for key, title in [("hotkey", "Region shortcut"), ("ocr_language", "OCR language(s)")]:
            field = QLineEdit(settings[key])
            self.fields[key] = field
            form.addRow(title, field)
        quality = QSpinBox()
        quality.setRange(1, 100)
        quality.setValue(settings["jpeg_quality"])
        self.fields["jpeg_quality"] = quality
        form.addRow("JPEG quality (white background)", quality)
        for key, title in [("auto_copy", "Copy automatically after capture"),
                           ("auto_history", "Save captures automatically to history"),
                           ("close_to_tray", "Closing the window minimises to tray")]:
            field = QCheckBox(title)
            field.setChecked(settings[key])
            self.fields[key] = field
            form.addRow(field)
        layout.addLayout(form)
        note = QLabel("History is off by default. Automatic history saves the initial capture before editing.\nChanging history folders opens a separate gallery; existing items stay in the old folder.\nRedacting never erases earlier exports or clipboard copies.\nOCR stays on this computer. Tesseract and the chosen languages are installed separately.")
        note.setWordWrap(True)
        layout.addWidget(note)
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
            if not values["save_dir"] or not values["history_dir"]:
                raise ValueError("Choose a save folder and a history folder.")
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
