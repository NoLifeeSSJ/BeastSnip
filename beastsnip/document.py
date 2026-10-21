"""Resolution-independent annotation model and flattened image output."""
from copy import deepcopy
from dataclasses import dataclass, field
import math

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QObject, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF

from .config import atomic_bytes


@dataclass
class Annotation:
    kind: str
    points: list = field(default_factory=list)
    color: str = "#a78bfa"
    width: int = 4
    text: str = ""
    font_size: int = 24
    number: int = 1
    offset: QPointF = field(default_factory=QPointF)

    def bounds(self):
        if not self.points:
            return QRectF()
        if self.kind == "text":
            font = QFont("Segoe UI")
            font.setPixelSize(self.font_size)
            from PySide6.QtGui import QFontMetricsF
            metrics = QFontMetricsF(font)
            lines = self.text.splitlines() or [""]
            return QRectF(self.points[0].x(), self.points[0].y(), max(metrics.horizontalAdvance(line) for line in lines) + 10, metrics.height() * len(lines) + 10)
        if self.kind == "number":
            p = self.points[0]
            return QRectF(p.x() - 19, p.y() - 19, 38, 38)
        xs, ys = [p.x() for p in self.points], [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-self.width, -self.width, self.width, self.width)

    def paint(self, painter):
        painter.save()
        painter.translate(self.offset)
        color = QColor(self.color)
        pen = QPen(color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        points = self.points
        if not points:
            painter.restore()
            return
        rect = QRectF(points[0], points[-1]).normalized()
        if self.kind in ("pen", "highlight"):
            if self.kind == "highlight":
                color.setAlpha(85)
                pen.setColor(color)
                pen.setWidth(max(12, self.width * 5))
                painter.setPen(pen)
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            if len(points) == 1:
                painter.drawPoint(points[0])
            else:
                painter.drawPath(path)
        elif self.kind == "arrow":
            a, b = points[0], points[-1]
            painter.drawLine(a, b)
            angle = math.atan2(b.y() - a.y(), b.x() - a.x())
            size = max(14, self.width * 4)
            head = QPolygonF([b, b - QPointF(math.cos(angle - .45) * size, math.sin(angle - .45) * size), b - QPointF(math.cos(angle + .45) * size, math.sin(angle + .45) * size)])
            painter.setBrush(color)
            painter.drawPolygon(head)
        elif self.kind in ("rect", "filled", "redact", "ellipse"):
            if self.kind == "redact":
                # Opaque, exact pixels: never use translucent pen edges for redaction.
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.fillRect(rect.toAlignedRect(), QColor("#000000"))
            else:
                if self.kind == "filled":
                    painter.setBrush(color)
                if self.kind == "ellipse":
                    painter.drawEllipse(rect)
                else:
                    painter.drawRect(rect)
        elif self.kind == "text":
            font = QFont("Segoe UI")
            font.setPixelSize(self.font_size)
            painter.setFont(font)
            painter.drawText(self.bounds(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.text)
        elif self.kind == "number":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(self.bounds())
            font = QFont("Segoe UI", 12, QFont.Weight.Bold)
            font.setPixelSize(23)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(self.bounds(), Qt.AlignmentFlag.AlignCenter, str(self.number))
        painter.restore()


class Document(QObject):
    changed = Signal()

    def __init__(self, image, parent=None):
        super().__init__(parent)
        if image.isNull():
            raise ValueError("The image could not be opened.")
        self.base = image.convertToFormat(QImage.Format.Format_ARGB32)
        self.base.setDevicePixelRatio(1)
        self.annotations = []
        self.undo_stack, self.redo_stack = [], []
        self.revision, self.saved_revision = 0, 0
        self._next_revision = 0
        self.history_id = None
        self.ocr_text = ""
        self.saved_ocr_text = ""

    @property
    def dirty(self):
        return self.revision != self.saved_revision or self.ocr_text != self.saved_ocr_text

    def snapshot(self):
        return QImage(self.base), deepcopy(self.annotations), self.revision, self.ocr_text

    def checkpoint(self):
        self.undo_stack.append(self.snapshot())
        # Whole images are implicitly shared until edited. Bound undo history.
        if len(self.undo_stack) > 35:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._next_revision += 1
        self.revision = self._next_revision
        self.ocr_text = ""  # Never retain stale OCR after redaction or edits.

    def add(self, item):
        self.checkpoint()
        self.annotations.append(deepcopy(item))
        self.changed.emit()

    def replace(self, index, item):
        self.checkpoint()
        self.annotations[index] = deepcopy(item)
        self.changed.emit()

    def remove(self, index):
        self.checkpoint()
        del self.annotations[index]
        self.changed.emit()

    def _restore(self, source, destination):
        if not source:
            return
        destination.append(self.snapshot())
        self.base, self.annotations, self.revision, self.ocr_text = source.pop()
        self.changed.emit()

    def undo(self):
        self._restore(self.undo_stack, self.redo_stack)

    def redo(self):
        self._restore(self.redo_stack, self.undo_stack)

    def flatten(self):
        result = self.base.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for item in self.annotations:
            item.paint(painter)
        painter.end()
        # Copy into a fresh buffer so source metadata/text never enters exports.
        clean = QImage(result.size(), QImage.Format.Format_ARGB32)
        clean.fill(Qt.GlobalColor.transparent)
        painter = QPainter(clean)
        painter.drawImage(0, 0, result)
        painter.end()
        return clean

    def crop(self, rect):
        region = rect.toAlignedRect().intersected(self.base.rect())
        if region.width() < 2 or region.height() < 2:
            raise ValueError("Select an area at least 2 × 2 pixels.")
        flattened = self.flatten()
        self.checkpoint()
        self.base = flattened.copy(region)
        self.annotations = []
        self.changed.emit()

    def mark_saved(self, include_ocr=False):
        self.saved_revision = self.revision
        if include_ocr:
            self.saved_ocr_text = self.ocr_text
        self.changed.emit()


def encode_image(image, format="PNG", quality=92):
    # Repaint any input to strip image text, profiles, source metadata and layers.
    result = QImage(image.size(), QImage.Format.Format_RGB32 if format.upper() in ("JPG", "JPEG") else QImage.Format.Format_ARGB32)
    result.fill(Qt.GlobalColor.white if format.upper() in ("JPG", "JPEG") else Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawImage(0, 0, image)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not result.save(buffer, format, quality):
        raise OSError("The image encoder could not save this image.")
    return bytes(data)


def save_image(path, image, quality=92):
    from pathlib import Path
    fmt = "JPEG" if Path(path).suffix.lower() in (".jpg", ".jpeg") else "PNG"
    atomic_bytes(path, encode_image(image, fmt, quality))
