"""Visible-pixel vertical scrolling capture with conservative overlap matching."""
from collections import Counter, defaultdict

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import windows

QUANTISE = bytes((value // 16) * 16 for value in range(256))


class AlignmentError(ValueError):
    pass


def row_signatures(image):
    width = min(192, image.width())
    sample = image.scaled(width, image.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    data = bytes(sample.constBits())
    stride = sample.bytesPerLine()
    # Side margins and scrollbars must not outweigh the scrolling content.
    left, right = max(1, width // 12), max(2, width - width // 12)
    return [data[y * stride + left:y * stride + right].translate(QUANTISE) for y in range(image.height())]


def scroll_offset(previous, current):
    if previous.size() != current.size():
        raise AlignmentError('The capture area changed size. Start a new scrolling capture.')
    before, after = row_signatures(previous), row_signatures(current)
    if before == after:
        return 0
    height = len(before)
    minimum_overlap = max(32, height // 6)
    index = defaultdict(list)
    for y, row in enumerate(before):
        if max(row) - min(row) >= 32:
            index[row].append(y)
    votes = Counter()
    for y in range(0, height - minimum_overlap, 3):
        for old in index.get(after[y], [])[:80]:
            offset = old - y
            if 8 <= offset <= height - minimum_overlap:
                votes[offset] += 1
    scored = []
    for offset, _ in votes.most_common(16):
        useful = [(a, b) for a, b in zip(before[offset:], after[:height - offset]) if max(a) - min(a) >= 32 or max(b) - min(b) >= 32]
        if len(useful) >= 16:
            matches = sum(a == b for a, b in useful)
            score = matches / len(useful)
            if score >= .82:
                scored.append((score, matches, offset))
    scored.sort(reverse=True)
    if not scored or (len(scored) > 1 and scored[1][0] >= scored[0][0] - .015 and scored[1][1] >= scored[0][1] * .8):
        raise AlignmentError('The overlap is unclear. Scroll a smaller distance, then Add Frame. Exclude fixed toolbars and sticky headers from the selected area.')
    return scored[0][2]


class ImageStitcher:
    def __init__(self, max_pixels=40_000_000, max_height=32000):
        self.frames, self.previous = [], None
        self.width = self.height = self.count = 0
        self.max_pixels, self.max_height = max_pixels, max_height

    def append(self, image):
        if image.isNull() or image.height() < 64 or image.width() < 64:
            raise AlignmentError('Select a scrolling content area at least 64 × 64 pixels.')
        offset = image.height() if self.previous is None else scroll_offset(self.previous, image)
        if offset == 0:
            return False
        height = self.height + offset
        if height > self.max_height or image.width() * height > self.max_pixels:
            raise AlignmentError('The image size limit was reached. Finish this capture and start another for the remaining content.')
        self.frames.append(image.copy(0, image.height() - offset, image.width(), offset))
        self.previous = QImage(image)
        self.width, self.height, self.count = image.width(), height, self.count + 1
        return True

    def image(self):
        if not self.frames:
            raise AlignmentError('No frames have been captured yet.')
        image = QImage(self.width, self.height, QImage.Format.Format_ARGB32)
        if image.isNull():
            raise MemoryError('There is not enough memory for this scrolling capture.')
        image.fill(Qt.GlobalColor.white)
        painter, y = QPainter(image), 0
        for frame in self.frames:
            painter.drawImage(0, y, frame)
            y += frame.height()
        painter.end()
        return image


class ScrollSetupDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('BeastSnip · Scrolling capture')
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        title = QLabel('Capture a longer view')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        note = QLabel('Select only the scrolling content after you start. Leave browser tabs, toolbars and sticky headers outside the selection. Keep the target window visible.\n\nAutomatic mode scrolls down for you. Manual mode lets you scroll, then Add Frame. Finish saves the joined image; Cancel discards it.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.automatic = QCheckBox('Scroll automatically')
        self.automatic.setChecked(True)
        form.addRow(self.automatic)
        self.frames = QSpinBox()
        self.frames.setRange(2, 40)
        self.frames.setValue(20)
        form.addRow('Frame limit', self.frames)
        self.interval = QSpinBox()
        self.interval.setRange(700, 3000)
        self.interval.setSingleStep(100)
        self.interval.setValue(1000)
        self.interval.setSuffix(' ms')
        form.addRow('Wait after each scroll', self.interval)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Select content area')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ScrollHUD(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.controller = controller

    def closeEvent(self, event):
        if not self.controller.done:
            self.controller.cancel()
        event.accept()


class ScrollController(QObject):
    captured = Signal(object)
    cancelled = Signal()

    def __init__(self, rect, automatic=True, frame_limit=20, interval=1000, parent=None):
        super().__init__(parent)
        self.rect = QRect(rect)
        self.automatic, self.frame_limit, self.interval = automatic, frame_limit, interval
        self.stitcher, self.unchanged, self.done, self.busy = ImageStitcher(), 0, False, False
        self.finish_requested = False
        self.target = windows.window_at_point(rect.center())
        self.start_bounds = windows.window_rectangle(self.target)
        if not self.start_bounds.contains(self.rect):
            raise ValueError('Select scrolling content inside one visible window.')
        self.hud = ScrollHUD(self)
        self.hud.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.hud.setWindowTitle('BeastSnip · Scrolling capture')
        self.hud.setFixedWidth(390)
        layout = QVBoxLayout(self.hud)
        self.status = QLabel('Preparing the first frame…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        hint = QLabel('Esc pauses automatic capture. Finish keeps the joined image.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        actions = QHBoxLayout()
        for text, callback in [('Add Frame', self.manual_add_frame), ('Finish', self.finish), ('Cancel', self.cancel)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        available = QApplication.primaryScreen().availableGeometry()
        self.hud.move(available.right() - 410, available.top() + 20)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)
        self.escape_timer = QTimer(self)
        self.escape_timer.timeout.connect(self.check_escape)

    def start(self):
        self.escape_timer.start(50)
        self.add_frame()

    def check_escape(self):
        if windows.escape_pressed():
            self.automatic = False
            self.timer.stop()
            self.status.setText('Paused. Scroll manually and Add Frame, or Finish to save the captured portion.')

    def validate_target(self):
        if windows.window_rectangle(self.target) != self.start_bounds:
            raise AlignmentError('The target window moved or resized. Finish the captured portion or start again.')
        for point in (self.rect.topLeft() + QPoint(2, 2), self.rect.center(), self.rect.bottomRight() - QPoint(2, 2)):
            if windows.window_at_point(point) != self.target:
                raise AlignmentError('The target is covered by another window. Uncover it before adding another frame.')

    def add_frame(self):
        if self.done or self.busy:
            return
        self.timer.stop()
        self.busy = True
        self.hud.hide()
        QTimer.singleShot(180, self.snapshot)

    def manual_add_frame(self):
        self.automatic = False
        self.timer.stop()
        self.add_frame()

    def snapshot(self):
        if self.done:
            return
        try:
            self.validate_target()
            added = self.stitcher.append(windows.grab_pixels(self.rect))
            self.unchanged = 0 if added else self.unchanged + 1
            self.status.setText(f'{self.stitcher.count} frames · {self.stitcher.width} × {self.stitcher.height} px')
            if self.stitcher.count >= self.frame_limit:
                self.automatic = False
                self.status.setText(self.status.text() + '\nFrame limit reached. Finish to save, or Add Frame manually.')
            elif self.automatic and self.unchanged >= 3:
                self.busy = False
                self.finish()
                return
            if self.automatic:
                self.timer.start(250)
        except Exception as error:
            self.automatic = False
            self.status.setText(str(error))
        self.busy = False
        if self.finish_requested:
            self.finish_requested = False
            self.finish()
            return
        self.hud.show()

    def advance(self):
        if self.done or self.busy or not self.automatic:
            return
        self.hud.hide()
        try:
            self.validate_target()
            windows.scroll_at(self.rect.center(), -3)
            self.busy = True
            QTimer.singleShot(self.interval, self.snapshot)
        except Exception as error:
            self.automatic = False
            self.status.setText(str(error))
            self.hud.show()

    def finish(self):
        if self.done:
            return
        if self.busy:
            self.automatic = False
            self.timer.stop()
            self.finish_requested = True
            self.status.setText('Finishing after the current frame…')
            return
        try:
            image = self.stitcher.image()
        except Exception as error:
            self.status.setText(str(error))
            return
        self.cleanup()
        self.captured.emit(image)

    def cancel(self):
        if not self.done:
            self.cleanup()
            self.cancelled.emit()

    def cleanup(self):
        if self.done:
            return
        self.done = True
        self.timer.stop()
        self.escape_timer.stop()
        self.hud.hide()
        self.hud.deleteLater()
