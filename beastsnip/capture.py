from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import windows


class RegionOverlay(QWidget):
    def __init__(self, session, screen, physical):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.session, self.physical = session, physical
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("BeastSnip region selection")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.local_image = session.frozen.copy(physical.translated(-session.bounds.topLeft()))

    def native_to_local(self, rect):
        return QRectF((rect.x() - self.physical.x()) * self.width() / self.physical.width(),
                      (rect.y() - self.physical.y()) * self.height() / self.physical.height(),
                      rect.width() * self.width() / self.physical.width(), rect.height() * self.height() / self.physical.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawImage(self.rect(), self.local_image)
        p.fillRect(self.rect(), QColor(0, 0, 0, 115))
        selection = self.session.selection()
        if selection is not None:
            r = self.native_to_local(selection)
            p.save()
            p.setClipRect(r)
            p.drawImage(self.rect(), self.local_image)
            p.restore()
            p.setPen(QPen(QColor("#bba1ff"), 2))
            p.drawRect(r)
        p.setPen(QColor("#ffffff"))
        p.drawText(20, 32, "Drag to select  •  M magnifier  •  Esc to cancel" if selection is None else f"{selection.width()} × {selection.height()} px  •  M magnifier  •  Esc to cancel")
        cursor = getattr(self.session, 'cursor_point', None)
        if cursor is not None and getattr(self.session, 'magnifier', False) and self.physical.contains(cursor):
            self.paint_magnifier(p, cursor)

    def paint_magnifier(self, painter, cursor):
        x = (cursor.x() - self.physical.x()) * self.width() / self.physical.width()
        y = (cursor.y() - self.physical.y()) * self.height() / self.physical.height()
        left = min(max(8, round(x + 26)), max(8, self.width() - 162))
        top = round(y + 26)
        if top + 182 > self.height():
            top = max(8, round(y - 194))
        source = QRect(cursor.x() - self.physical.x() - 10, cursor.y() - self.physical.y() - 10, 21, 21)
        target = QRect(left + 4, top + 4, 146, 146)
        painter.fillRect(QRect(left, top, 154, 180), QColor('#1b1b2b'))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, self.local_image.copy(source))
        painter.setPen(QPen(QColor('#c6a4ff'), 1))
        painter.drawRect(target)
        center = target.center()
        painter.drawLine(center.x() - 9, center.y(), center.x() + 9, center.y())
        painter.drawLine(center.x(), center.y() - 9, center.x(), center.y() + 9)
        painter.setPen(QColor('#ffffff'))
        painter.drawText(left + 7, top + 169, f'{cursor.x()}, {cursor.y()} px')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.session.begin()
        elif event.button() == Qt.MouseButton.RightButton:
            self.session.cancel()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.session.finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.session.cancel()
        elif event.key() == Qt.Key.Key_M:
            self.session.magnifier = not self.session.magnifier
            for overlay in self.session.overlays:
                overlay.update()


class RegionSession(QObject):
    captured = Signal(object)
    cancelled = Signal()

    def __init__(self, parent=None, magnifier=True):
        super().__init__(parent)
        monitors = windows.monitor_rectangles()
        mapped = windows.map_displays(QApplication.screens(), monitors)
        self.bounds = QRect(monitors[0][1])
        for _, physical in monitors[1:]:
            self.bounds = self.bounds.united(physical)
        self.frozen = windows.grab_pixels(self.bounds)
        self.start_point, self.end_point = None, None
        self.cursor_point, self.magnifier, self.selected_rect = None, magnifier, None
        self.overlays, self.done = [], False
        for display in mapped:
            self.overlays.append(RegionOverlay(self, display.screen, display.physical))
        if not self.overlays:
            raise RuntimeError("No displays are available for region capture.")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)

    def show(self):
        for overlay in self.overlays:
            overlay.show()
            overlay.raise_()
        self.overlays[0].activateWindow()
        self.timer.start(16)

    def begin(self):
        self.start_point = windows.cursor_position()
        self.end_point = QPoint(self.start_point)

    def selection(self):
        if self.start_point is None:
            return None
        a, b = self.start_point, self.end_point
        return QRect(min(a.x(), b.x()), min(a.y(), b.y()), abs(a.x() - b.x()), abs(a.y() - b.y())).intersected(self.bounds)

    def poll(self):
        if windows.user32.GetAsyncKeyState(0x1B) & 0x8000:
            self.cancel()
            return
        self.cursor_point = windows.cursor_position()
        if self.start_point is not None:
            self.end_point = QPoint(self.cursor_point)
            if not windows.user32.GetAsyncKeyState(0x01) & 0x8000:
                self.finish()
                return
        for overlay in self.overlays:
            overlay.update()

    def cleanup(self):
        self.done = True
        self.timer.stop()
        for overlay in self.overlays:
            overlay.close()
        self.overlays.clear()

    def finish(self):
        if self.done or self.start_point is None:
            return
        self.end_point = windows.cursor_position()
        rect = self.selection()
        if rect.width() < 2 or rect.height() < 2:
            self.cancel()
            return
        image = self.frozen.copy(rect.translated(-self.bounds.topLeft()))
        self.selected_rect = QRect(rect)
        self.cleanup()
        self.captured.emit(image)

    def cancel(self):
        if self.done:
            return
        self.cleanup()
        self.cancelled.emit()
