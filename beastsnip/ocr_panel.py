"""Readable OCR results with an expandable view of the same editable text."""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QSpinBox, QTextEdit, QVBoxLayout, QWidget)


class OCRTextEdit(QTextEdit):
    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride:
            # Editing/copying OCR must never invoke the image editor's actions.
            event.accept()
            return True
        return super().event(event)


class OCRTextView(QWidget):
    def __init__(self, size=12, wrap=True, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Text size"))
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 24)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(size)
        self.font_size.setToolTip("Change the reading size without changing the extracted text")
        controls.addWidget(self.font_size)
        controls.addStretch()
        self.wrap = QCheckBox("Wrap lines")
        self.wrap.setChecked(wrap)
        controls.addWidget(self.wrap)
        layout.addLayout(controls)
        self.text_edit = OCRTextEdit()
        self.text_edit.setObjectName("ocrTextEditor")
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setMinimumHeight(180)
        self.text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.text_edit.setPlaceholderText("No readable text found. Try selecting a clearer area of the image.")
        self.text_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.addWidget(self.text_edit, 1)
        self.font_size.valueChanged.connect(self.apply_font_size)
        self.wrap.toggled.connect(self.apply_wrap)
        self.apply_font_size(size)
        self.apply_wrap(wrap)

    def apply_font_size(self, size):
        font = QFont("Segoe UI")
        font.setPointSize(size)
        self.text_edit.setFont(font)
        self.text_edit.document().setDefaultFont(font)
        self.text_edit.setStyleSheet(f"font-size: {size}pt; padding: 12px;")

    def apply_wrap(self, wrap):
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if wrap else QTextEdit.LineWrapMode.NoWrap)

    def copy_text(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())


class OCRTextDialog(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle("BeastSnip · Extracted text")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(480, 360)
        available = panel.screen().availableGeometry()
        self.resize(min(960, available.width() - 60), min(720, available.height() - 80))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        heading = QLabel("Extracted text")
        heading.setObjectName("ocrHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Edit and copy your text. Changes also appear beside the image."))
        self.view = OCRTextView(panel.view.font_size.value(), panel.view.wrap.isChecked())
        self.text_edit = self.view.text_edit
        self.sync_from_panel()
        layout.addWidget(self.view, 1)
        # Separate layouts let each view wrap to its own width. Text and reading
        # controls stay in sync without resetting the active editor's undo stack.
        self.text_edit.textChanged.connect(self.sync_to_panel)
        # Document notifications also reach us when the editor blocks widget
        # signals while clearing stale OCR after an image edit or redaction.
        panel.text_edit.document().contentsChanged.connect(self.sync_from_panel)
        self.view.font_size.valueChanged.connect(panel.view.font_size.setValue)
        panel.view.font_size.valueChanged.connect(self.view.font_size.setValue)
        self.view.wrap.toggled.connect(panel.view.wrap.setChecked)
        panel.view.wrap.toggled.connect(self.view.wrap.setChecked)
        footer = QHBoxLayout()
        copy = QPushButton("Copy Text")
        copy.clicked.connect(self.view.copy_text)
        footer.addWidget(copy)
        footer.addStretch()
        done = QPushButton("Back to Image")
        done.clicked.connect(self.accept)
        footer.addWidget(done)
        layout.addLayout(footer)

    def sync_from_panel(self):
        text = self.panel.text_edit.toPlainText()
        if self.text_edit.toPlainText() != text:
            self.text_edit.setPlainText(text)

    def sync_to_panel(self):
        text = self.text_edit.toPlainText()
        if self.panel.text_edit.toPlainText() != text:
            self.panel.text_edit.setPlainText(text)


class OCRPanel(QWidget):
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ocrPanel")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel("Extracted text")
        title.setObjectName("ocrHeading")
        layout.addWidget(title)
        hint = QLabel("Edit or copy below. Save to History to keep the text.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.view = OCRTextView()
        self.text_edit = self.view.text_edit
        layout.addWidget(self.view, 1)
        footer = QHBoxLayout()
        self.copy_button = QPushButton("Copy Text")
        self.copy_button.clicked.connect(self.view.copy_text)
        footer.addWidget(self.copy_button)
        self.expand_button = QPushButton("Expand Text")
        self.expand_button.setToolTip("Open a large, resizable text window")
        self.expand_button.clicked.connect(self.expand)
        footer.addWidget(self.expand_button)
        footer.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close_requested.emit)
        footer.addWidget(close)
        layout.addLayout(footer)

    def expand(self):
        dialog = OCRTextDialog(self)
        # A modal reader avoids including our own OCR window in a new capture.
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
