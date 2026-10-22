"""Resolution-independent annotation model and flattened image output."""
from copy import deepcopy
from dataclasses import dataclass, field
import math

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QObject, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF

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
    opacity: int = 100
    line_style: str = 'solid'
    cap: str = 'round'
    fill_style: str = 'none'
    arrow_heads: str = 'end'
    smooth: bool = False

    def path(self):
        path = QPainterPath()
        if not self.points:
            return path
        path.moveTo(self.points[0])
        if self.smooth and len(self.points) > 2:
            for a, b in zip(self.points[1:-1], self.points[2:]):
                path.quadTo(a, (a + b) / 2)
            path.lineTo(self.points[-1])
        else:
            for point in self.points[1:]:
                path.lineTo(point)
        return path

    def hit_path(self):
        """Annotation geometry, without its scene offset, for selection/erasing."""
        path = QPainterPath()
        if not self.points:
            return path
        rect = QRectF(self.points[0], self.points[-1]).normalized()
        if self.kind in ('pen', 'brush', 'highlight', 'line', 'arrow'):
            path = self.path()
            if len(self.points) == 1 or path.isEmpty():
                path.addEllipse(self.points[0], 1, 1)
        elif self.kind == 'ellipse':
            path.addEllipse(rect)
        elif self.kind == 'round_rect':
            path.addRoundedRect(rect, min(16, rect.width() / 4), min(16, rect.height() / 4))
        elif self.kind == 'number':
            path.addEllipse(self.bounds())
        else:
            path.addRect(self.bounds() if self.kind in ('text', 'number') else rect)
        if self.kind in ('text', 'number', 'filled', 'redact') or self.fill_style != 'none':
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(max(10, self.width * 5 if self.kind == 'highlight' else self.width + 6))
        result = stroker.createStroke(path)
        if self.kind == 'arrow':
            for polygon in self.head_polygons():
                head = QPainterPath(); head.addPolygon(polygon); head.closeSubpath()
                result = result.united(head).united(stroker.createStroke(head))
        return result

    def head_polygons(self):
        if self.kind != 'arrow' or self.arrow_heads == 'none' or len(self.points) < 2:
            return []
        a, b = self.points[0], self.points[-1]
        result = []
        for start, end in ([(a, b), (b, a)] if self.arrow_heads == 'both' else [(a, b)]):
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            size = max(14, self.width * 4)
            result.append(QPolygonF([end, end - QPointF(math.cos(angle - .45) * size, math.sin(angle - .45) * size), end - QPointF(math.cos(angle + .45) * size, math.sin(angle + .45) * size)]))
        return result

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
        margin = max(14, self.width * 4) if self.kind == 'arrow' else max(12, self.width * 2.5) if self.kind == 'highlight' else self.width + 2
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-margin, -margin, margin, margin)

    def paint(self, painter):
        painter.save()
        painter.translate(self.offset)
        # Redaction always remains fully opaque, regardless of drawing styles.
        painter.setOpacity(1 if self.kind == 'redact' else self.opacity / 100)
        color = QColor(self.color)
        pattern = {'solid': Qt.PenStyle.SolidLine, 'dash': Qt.PenStyle.DashLine, 'dot': Qt.PenStyle.DotLine}.get(self.line_style, Qt.PenStyle.SolidLine)
        pen = QPen(color, self.width, pattern, Qt.PenCapStyle.SquareCap if self.cap == 'square' else Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        points = self.points
        if not points:
            painter.restore()
            return
        rect = QRectF(points[0], points[-1]).normalized()
        if self.kind in ("pen", "brush", "highlight"):
            if self.kind == "highlight":
                color.setAlpha(85)
                pen.setColor(color)
                pen.setWidth(max(12, self.width * 5))
                painter.setPen(pen)
            if len(points) == 1:
                painter.drawPoint(points[0])
            else:
                painter.drawPath(self.path())
        elif self.kind in ('line', 'arrow'):
            a, b = points[0], points[-1]
            painter.drawLine(a, b)
            if self.kind == 'arrow' and self.arrow_heads != 'none':
                pen.setStyle(Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                for head in self.head_polygons():
                    painter.setBrush(color)
                    painter.drawPolygon(head)
        elif self.kind in ("rect", "round_rect", "filled", "redact", "ellipse"):
            if self.kind == "redact":
                # Opaque, exact pixels: never use translucent pen edges for redaction.
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.fillRect(rect.toAlignedRect(), QColor("#000000"))
            else:
                if self.kind == 'filled' or self.fill_style != 'none':
                    fill = QColor(color)
                    if self.fill_style == 'soft':
                        fill.setAlpha(64)
                    painter.setBrush(fill)
                if self.kind == "ellipse":
                    painter.drawEllipse(rect)
                elif self.kind == 'round_rect':
                    painter.drawRoundedRect(rect, min(16, rect.width() / 4), min(16, rect.height() / 4))
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
        self.advance_revision()

    def advance_revision(self):
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

    def remove(self, index, checkpoint=True):
        if checkpoint:
            self.checkpoint()
        else:
            self.advance_revision()
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
