from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QGraphicsItem,
    QGraphicsObject, QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget)

from .document import Annotation
from .ocr_panel import OCRPanel


class AnnotationItem(QGraphicsObject):
    def __init__(self, annotation, index, canvas):
        super().__init__()
        self.annotation, self.index, self.canvas = deepcopy(annotation), index, canvas
        self.setPos(annotation.offset)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def boundingRect(self):
        extra = max(12, self.annotation.width * 3) if self.annotation.kind in ("highlight", "arrow") else 5
        return self.annotation.bounds().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter, option, widget=None):
        item = deepcopy(self.annotation)
        item.offset = QPointF()
        item.paint(painter)
        if self.isSelected():
            pen = QPen(QColor("#d8caff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.pos() != self.annotation.offset:
            updated = deepcopy(self.annotation)
            updated.offset = QPointF(self.pos())
            canvas, index = self.canvas, self.index
            QTimer.singleShot(0, lambda: canvas.commit_move(index, updated))

    def mouseDoubleClickEvent(self, event):
        if self.annotation.kind == "text":
            text, ok = QInputDialog.getMultiLineText(self.canvas, "Edit text label", "Text", self.annotation.text)
            if ok and text:
                updated = deepcopy(self.annotation)
                updated.text = text
                canvas, index = self.canvas, self.index
                QTimer.singleShot(0, lambda: canvas.commit_move(index, updated))
        else:
            super().mouseDoubleClickEvent(event)


class Canvas(QGraphicsView):
    area_selected = Signal(object)
    zoom_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#101118"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.doc, self.tool, self.color = None, "select", "#a78bfa"
        self.stroke_width, self.font_size = 4, 24
        self.preview, self.preview_item, self.origin = None, None, None
        self.auto_fit, self.pan_point = True, None

    def set_document(self, doc):
        if self.doc:
            self.doc.changed.disconnect(self.rebuild)
        self.doc = doc
        self.doc.changed.connect(self.rebuild)
        self.auto_fit = True
        self.rebuild()
        QTimer.singleShot(0, self.fit_image)

    def rebuild(self):
        self.preview_item, self.preview = None, None
        self.scene().clear()
        if not self.doc:
            return
        background = self.scene().addPixmap(QPixmap.fromImage(self.doc.base))
        background.setZValue(-1000)
        self.scene().setSceneRect(QRectF(self.doc.base.rect()))
        for index, annotation in enumerate(self.doc.annotations):
            item = AnnotationItem(annotation, index, self)
            self.scene().addItem(item)
            item.setZValue(index)
            item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if self.tool == "select" else Qt.MouseButton.NoButton)
        if self.auto_fit:
            self.fit_image()

    def set_tool(self, tool):
        self.cancel()
        self.tool = tool
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool == "pan" else QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if tool == "pan" else Qt.CursorShape.ArrowCursor if tool == "select" else Qt.CursorShape.CrossCursor)
        for item in self.scene().items():
            if isinstance(item, AnnotationItem):
                item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if tool == "select" else Qt.MouseButton.NoButton)

    def commit_move(self, index, annotation):
        if self.doc and 0 <= index < len(self.doc.annotations):
            self.doc.replace(index, annotation)

    def selected_index(self):
        return next((item.index for item in self.scene().selectedItems() if isinstance(item, AnnotationItem)), None)

    def delete_selected(self):
        index = self.selected_index()
        if index is not None:
            self.doc.remove(index)

    def cancel(self):
        if self.preview_item:
            self.scene().removeItem(self.preview_item)
        self.preview, self.preview_item, self.origin = None, None, None
        self.scene().clearSelection()

    def fit_image(self):
        if not self.doc:
            return
        self.auto_fit = True
        self.fitInView(self.sceneRect().adjusted(-16, -16, 16, 16), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(round(self.transform().m11() * 100))

    def actual_size(self):
        self.auto_fit = False
        self.resetTransform()
        # One image pixel per physical display pixel, including high-DPI screens.
        self.scale(1 / self.devicePixelRatioF(), 1 / self.devicePixelRatioF())
        self.zoom_changed.emit(round(self.transform().m11() * 100))

    def zoom(self, factor):
        proposed = self.transform().m11() * factor
        if .02 <= proposed <= 20:
            self.auto_fit = False
            self.scale(factor, factor)
            self.zoom_changed.emit(round(self.transform().m11() * 100))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit_image()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    def image_point(self, event):
        p = self.mapToScene(event.position().toPoint())
        return QPointF(max(0, min(self.doc.base.width(), p.x())), max(0, min(self.doc.base.height(), p.y())))

    def mousePressEvent(self, event):
        if not self.doc:
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_point = event.position()
            return
        if event.button() != Qt.MouseButton.LeftButton or self.tool in ("select", "pan"):
            return super().mousePressEvent(event)
        p = self.image_point(event)
        if self.tool == "text":
            text, ok = QInputDialog.getMultiLineText(self, "Text label", "Text")
            if ok and text:
                self.doc.add(Annotation("text", [p], self.color, self.stroke_width, text, self.font_size))
            return
        if self.tool == "number":
            number = max((a.number for a in self.doc.annotations if a.kind == "number"), default=0) + 1
            self.doc.add(Annotation("number", [p], self.color, number=number))
            return
        self.origin = p
        self.preview = Annotation(self.tool, [p, p], self.color, self.stroke_width)
        self.update_preview()

    def update_preview(self):
        if self.preview_item:
            self.scene().removeItem(self.preview_item)
        if self.tool in ("crop", "ocr"):
            pen = QPen(QColor("#c4a8ff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.preview_item = self.scene().addRect(QRectF(self.preview.points[0], self.preview.points[-1]).normalized(), pen)
        else:
            self.preview_item = AnnotationItem(self.preview, -1, self)
            self.preview_item.setFlags(QGraphicsItem.GraphicsItemFlag(0))
            self.scene().addItem(self.preview_item)
        self.preview_item.setZValue(100000)

    def mouseMoveEvent(self, event):
        if self.pan_point is not None:
            delta = event.position() - self.pan_point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            self.pan_point = event.position()
            return
        if self.preview:
            p = self.image_point(event)
            if self.tool in ("pen", "highlight"):
                self.preview.points.append(p)
            else:
                self.preview.points[-1] = p
            self.update_preview()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_point = None
            return
        if self.preview and event.button() == Qt.MouseButton.LeftButton:
            item, tool = self.preview, self.tool
            rect = QRectF(item.points[0], self.image_point(event)).normalized()
            if tool not in ("pen", "highlight"):
                item.points[-1] = self.image_point(event)
            self.cancel()
            if tool == "crop":
                if rect.width() >= 2 and rect.height() >= 2:
                    self.doc.crop(rect)
            elif tool == "ocr":
                if rect.width() >= 2 and rect.height() >= 2:
                    self.area_selected.emit(rect)
            elif tool in ("pen", "highlight") or QLineF(item.points[0], item.points[-1]).length() >= 2:
                self.doc.add(item)
            return
        super().mouseReleaseEvent(event)


class Editor(QWidget):
    copy_requested = Signal()
    save_requested = Signal()
    history_requested = Signal()
    pin_requested = Signal()
    ocr_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tools = QButtonGroup(self)
        self.tools.setExclusive(True)
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 4, 4, 4)
        self.canvas = Canvas()
        for tool, label, tip in [
            ("select", "Select", "Select, move or delete annotations; double-click a text label to edit"),
            ("pan", "Pan", "Drag the image; middle mouse also pans"), ("pen", "Pen", "Freehand pen"),
            ("highlight", "Highlight", "Translucent highlighter"), ("arrow", "Arrow", "Draw an arrow"),
            ("rect", "Box", "Outlined rectangle"), ("filled", "Fill", "Filled rectangle"),
            ("ellipse", "Ellipse", "Outlined ellipse"), ("text", "Text", "Add a text label"),
            ("number", "Step", "Automatically numbered marker"), ("redact", "Redact", "Opaque black block; flatten on copy or export"),
            ("crop", "Crop", "Drag to crop; crop flattens objects, undo restores them"),
        ]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, t=tool: self.canvas.set_tool(t))
            self.tools.addButton(button)
            if tool == "select":
                button.setChecked(True)
                self.select_button = button
            row.addWidget(button)
        row.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(bar)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(76)
        layout.addWidget(scroll)
        controls = QHBoxLayout()
        colour = QPushButton("Colour")
        colour.clicked.connect(self.choose_colour)
        controls.addWidget(colour)
        controls.addWidget(QLabel("Stroke"))
        width = QSpinBox()
        width.setRange(1, 40)
        width.setValue(4)
        width.valueChanged.connect(lambda n: self.change_size("stroke_width", "width", n))
        controls.addWidget(width)
        controls.addWidget(QLabel("Text px"))
        size = QSpinBox()
        size.setRange(8, 160)
        size.setValue(24)
        size.valueChanged.connect(lambda n: self.change_size("font_size", "font_size", n))
        controls.addWidget(size)
        self.undo_button = self.button(controls, "Undo", lambda: self.canvas.doc.undo() if self.canvas.doc else None)
        self.redo_button = self.button(controls, "Redo", lambda: self.canvas.doc.redo() if self.canvas.doc else None)
        self.button(controls, "Delete", self.canvas.delete_selected)
        controls.addStretch()
        self.button(controls, "−", lambda: self.canvas.zoom(1 / 1.2))
        self.zoom_label = QLabel("100%")
        controls.addWidget(self.zoom_label)
        self.canvas.zoom_changed.connect(lambda n: self.zoom_label.setText(f"{n}%"))
        self.button(controls, "+", lambda: self.canvas.zoom(1.2))
        self.button(controls, "Fit", self.canvas.fit_image)
        self.button(controls, "1:1", self.canvas.actual_size)
        layout.addLayout(controls)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("editorSplitter")
        self.splitter.setHandleWidth(9)
        self.splitter.setChildrenCollapsible(False)
        self.canvas.setMinimumSize(240, 180)
        self.splitter.addWidget(self.canvas)
        self.ocr_panel = OCRPanel()
        self.ocr_text = self.ocr_panel.text_edit
        self.ocr_text.textChanged.connect(self.ocr_text_edited)
        self.ocr_panel.close_requested.connect(self.hide_ocr)
        self.splitter.addWidget(self.ocr_panel)
        self.ocr_panel.hide()
        self._ocr_width = None
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        layout.addWidget(self.splitter, 1)
        bottom = QHBoxLayout()
        self.button(bottom, "Copy Image", self.copy_requested.emit)
        self.button(bottom, "Save As…", self.save_requested.emit)
        self.button(bottom, "Save to History", self.history_requested.emit)
        self.ocr_button = self.button(bottom, "Extract Text", lambda: self.ocr_requested.emit(None))
        self.ocr_area_button = self.button(bottom, "OCR Area", lambda: self.canvas.set_tool("ocr"))
        self.button(bottom, "Pin on Screen", self.pin_requested.emit)
        bottom.addStretch()
        self.dimensions = QLabel()
        bottom.addWidget(self.dimensions)
        layout.addLayout(bottom)
        self.canvas.area_selected.connect(self.ocr_requested.emit)
        for sequence, callback in [
            ("Ctrl+C", self.copy_requested.emit), ("Ctrl+S", self.save_requested.emit),
            ("Ctrl+Z", lambda: self.canvas.doc.undo() if self.canvas.doc else None),
            ("Ctrl+Y", lambda: self.canvas.doc.redo() if self.canvas.doc else None),
            ("Ctrl+Shift+Z", lambda: self.canvas.doc.redo() if self.canvas.doc else None),
            ("Delete", self.canvas.delete_selected), ("Escape", self.escape),
        ]:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    @staticmethod
    def button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def escape(self):
        self.canvas.set_tool("select")
        self.select_button.setChecked(True)

    def choose_colour(self):
        color = QColorDialog.getColor(QColor(self.canvas.color), self, "Annotation colour")
        if color.isValid():
            self.canvas.color = color.name()
            index = self.canvas.selected_index()
            if index is not None:
                item = deepcopy(self.canvas.doc.annotations[index])
                item.color = color.name()
                self.canvas.doc.replace(index, item)

    def change_size(self, canvas_property, annotation_property, value):
        setattr(self.canvas, canvas_property, value)
        index = self.canvas.selected_index()
        if index is not None:
            item = deepcopy(self.canvas.doc.annotations[index])
            setattr(item, annotation_property, value)
            self.canvas.doc.replace(index, item)

    def set_document(self, doc):
        if self.canvas.doc:
            self.canvas.doc.changed.disconnect(self.update_state)
        self.canvas.set_document(doc)
        self.ocr_text.clear()
        self.hide_ocr()
        self.escape()
        doc.changed.connect(self.update_state)
        self.update_state()

    def update_state(self):
        doc = self.canvas.doc
        if doc:
            self.undo_button.setEnabled(bool(doc.undo_stack))
            self.redo_button.setEnabled(bool(doc.redo_stack))
            self.dimensions.setText(f"{doc.base.width()} × {doc.base.height()} px  ·  Editable session" + ("  ·  Unsaved" if doc.dirty else ""))
            if self.ocr_text.toPlainText() != doc.ocr_text:
                self.ocr_text.blockSignals(True)
                self.ocr_text.setPlainText(doc.ocr_text)
                self.ocr_text.blockSignals(False)

    def show_ocr(self, text):
        self.ocr_text.setPlainText(text)
        if self.ocr_panel.isHidden():
            self.ocr_panel.show()
            total = self.splitter.width() - self.splitter.handleWidth()
            desired = self._ocr_width or max(380, round(total * .36))
            width = max(self.ocr_panel.minimumWidth(), min(desired, total - self.canvas.minimumWidth()))
            self.splitter.setSizes([max(self.canvas.minimumWidth(), total - width), width])
        self.ocr_text.setFocus(Qt.FocusReason.OtherFocusReason)

    def hide_ocr(self):
        if not self.ocr_panel.isHidden():
            self._ocr_width = self.ocr_panel.width()
        self.ocr_panel.hide()

    def ocr_text_edited(self):
        if self.canvas.doc:
            self.canvas.doc.ocr_text = self.ocr_text.toPlainText()


    def copy_text(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.ocr_text.toPlainText())
