from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLineF, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QGraphicsItem,
    QGraphicsObject, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget)

from .document import Annotation
from .ocr_panel import OCRPanel
from .ui import icon, swatch_icon, tool_button
from .drawing import ColourPalette, StylePopup, DRAWING_TOOLS, FREEHAND, SHAPES, STROKED, defaults, validated_preferences


class AnnotationItem(QGraphicsObject):
    def __init__(self, annotation, index, canvas):
        super().__init__()
        self.annotation, self.index, self.canvas = deepcopy(annotation), index, canvas
        self.setPos(annotation.offset)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def boundingRect(self):
        extra = max(12, self.annotation.width * 3) if self.annotation.kind in ("highlight", "arrow") else 5
        return self.annotation.bounds().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        return self.annotation.hit_path()

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
    tool_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#101118"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.doc, self.tool, self.color = None, "select", "#a78bfa"
        self.stroke_width, self.font_size = 4, 24
        self.opacity, self.line_style, self.cap = 100, 'solid', 'round'
        self.fill_style, self.arrow_heads, self.smooth = 'none', 'end', True
        self.preferences = {}
        self.erasing, self.erased = False, False
        self._scene_revision = 0
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
        if self.doc:
            if self.doc.revision < self._scene_revision:
                self.erasing = False
            self._scene_revision = self.doc.revision
        selected = self.selected_index()
        self.preview_item, self.preview = None, None
        self.scene().blockSignals(True)
        self.scene().clear()
        if not self.doc:
            self.scene().blockSignals(False)
            return
        background = self.scene().addPixmap(QPixmap.fromImage(self.doc.base))
        background.setZValue(-1000)
        self.scene().setSceneRect(QRectF(self.doc.base.rect()))
        for index, annotation in enumerate(self.doc.annotations):
            item = AnnotationItem(annotation, index, self)
            self.scene().addItem(item)
            item.setZValue(index)
            item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if self.tool == "select" else Qt.MouseButton.NoButton)
            if index == selected:
                item.setSelected(True)
        self.scene().blockSignals(False)
        self.scene().selectionChanged.emit()
        if self.auto_fit:
            self.fit_image()

    def set_tool(self, tool):
        if self.tool in DRAWING_TOOLS:
            self.preferences[self.tool] = self.current_preferences()
        self.cancel()
        self.tool = tool
        if tool in DRAWING_TOOLS:
            for key, value in self.preferences.get(tool, defaults(tool)).items():
                setattr(self, 'stroke_width' if key == 'width' else key, value)
        self.tool_changed.emit(tool)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool == "pan" else QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if tool == "pan" else Qt.CursorShape.ArrowCursor if tool == "select" else Qt.CursorShape.CrossCursor)
        for item in self.scene().items():
            if isinstance(item, AnnotationItem):
                item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if tool == "select" else Qt.MouseButton.NoButton)

    def current_preferences(self):
        return {key: getattr(self, 'stroke_width' if key == 'width' else key) for key in defaults('pen')}

    def annotation(self, kind, points):
        return Annotation(kind, points, **self.current_preferences())

    def commit_move(self, index, annotation):
        if self.doc and 0 <= index < len(self.doc.annotations):
            self.doc.replace(index, annotation)

    def selected_index(self):
        return next((item.index for item in self.scene().selectedItems() if isinstance(item, AnnotationItem)), None)

    def delete_selected(self):
        index = self.selected_index()
        if index is not None:
            self.scene().clearSelection()
            self.doc.remove(index)

    def cancel(self):
        if self.preview_item:
            self.scene().removeItem(self.preview_item)
        self.preview, self.preview_item, self.origin = None, None, None
        self.erasing = False
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
        if self.tool == 'eraser':
            self.erasing, self.erased = True, False
            self.erase_at(p)
            return
        if self.tool == "text":
            text, ok = QInputDialog.getMultiLineText(self, "Text label", "Text")
            if ok and text:
                item = self.annotation('text', [p]); item.text = text
                self.doc.add(item)
            return
        if self.tool == "number":
            number = max((a.number for a in self.doc.annotations if a.kind == "number"), default=0) + 1
            item = self.annotation('number', [p]); item.number = number
            self.doc.add(item)
            return
        self.origin = p
        self.preview = self.annotation(self.tool, [p] if self.tool in FREEHAND else [p, p])
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
        if self.erasing:
            self.erase_at(self.image_point(event))
            return
        if self.pan_point is not None:
            delta = event.position() - self.pan_point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            self.pan_point = event.position()
            return
        if self.preview:
            p = self.image_point(event)
            p = self.constrain(p, event.modifiers())
            if self.tool in FREEHAND:
                if QLineF(self.preview.points[-1], p).length() >= .5:
                    self.preview.points.append(p)
            else:
                self.preview.points[-1] = p
            self.update_preview()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.erasing and event.button() == Qt.MouseButton.LeftButton:
            self.erase_at(self.image_point(event)); self.erasing = False
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_point = None
            return
        if self.preview and event.button() == Qt.MouseButton.LeftButton:
            item, tool = self.preview, self.tool
            rect = QRectF(item.points[0], self.image_point(event)).normalized()
            end = self.constrain(self.image_point(event), event.modifiers())
            if tool in FREEHAND:
                if item.points[-1] != end: item.points.append(end)
            else:
                item.points[-1] = end
            self.cancel()
            if tool == "crop":
                if rect.width() >= 2 and rect.height() >= 2:
                    self.doc.crop(rect)
            elif tool == "ocr":
                if rect.width() >= 2 and rect.height() >= 2:
                    self.area_selected.emit(rect)
            elif tool in FREEHAND or QLineF(item.points[0], item.points[-1]).length() >= 2:
                self.doc.add(item)
            return
        super().mouseReleaseEvent(event)

    def constrain(self, point, modifiers):
        if self.origin is None or not modifiers & Qt.KeyboardModifier.ShiftModifier:
            return point
        delta = point - self.origin
        if self.tool in SHAPES:
            size = max(abs(delta.x()), abs(delta.y()))
            point = self.origin + QPointF(size if delta.x() >= 0 else -size, size if delta.y() >= 0 else -size)
        elif self.tool in ('line', 'arrow'):
            import math
            angle = round(math.atan2(delta.y(), delta.x()) / (math.pi / 4)) * math.pi / 4
            distance = QLineF(self.origin, point).length()
            point = self.origin + QPointF(math.cos(angle) * distance, math.sin(angle) * distance)
        return QPointF(max(0, min(self.doc.base.width(), point.x())), max(0, min(self.doc.base.height(), point.y())))

    def erase_at(self, point):
        for item in self.scene().items(point):
            if isinstance(item, AnnotationItem) and item.index >= 0:
                self.doc.remove(item.index, checkpoint=not self.erased)
                self.erased = True
                break


TOOLS = [
    ("select", "Select", "V", "Select and move annotations; double-click a text label to edit"),
    ("pan", "Pan", "H", "Drag to pan; the middle mouse button also pans"),
    ("pen", "Pen", "P", "Draw freehand on the image"),
    ("brush", "Brush", "G", "Paint a broad freehand stroke; adjust size, opacity and smoothing"),
    ("highlight", "Highlight", "I", "Mark an area with translucent colour"),
    ("line", "Line", "L", "Draw a straight line; hold Shift for 45-degree angles"),
    ("arrow", "Arrow", "A", "Drag from the tail to the tip of an arrow"),
    ("rect", "Box", "B", "Draw an outlined rectangle"),
    ("round_rect", "Rounded", "U", "Draw a rounded box; hold Shift for equal sides"),
    ("filled", "Fill", "F", "Draw a filled rectangle"),
    ("ellipse", "Ellipse", "O", "Draw an outlined ellipse"),
    ("text", "Text", "T", "Click the image to add an editable text label"),
    ("number", "Step", "N", "Click to place the next numbered marker"),
    ("eraser", "Eraser", "E", "Erase whole annotations; leaves source pixels unchanged; drag erases in one undo step"),
    ("redact", "Redact", "R", "Draw an opaque black block over sensitive information"),
    ("crop", "Crop", "C", "Drag to crop; undo restores the image and editable objects"),
]


class Editor(QWidget):
    preferences_changed = Signal(object)
    copy_requested = Signal()
    save_requested = Signal()
    quicksave_requested = Signal()
    folder_requested = Signal()
    history_requested = Signal()
    pin_requested = Signal()
    ocr_requested = Signal(object)
    project_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = Canvas()
        self.tools = QButtonGroup(self)
        self.tools.setExclusive(True)
        self.tool_buttons = {}
        self.focus_mode = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        workspace = QHBoxLayout()
        workspace.setSpacing(12)
        self.rail = QWidget()
        self.rail.setObjectName('toolRail')
        self.rail.setFixedWidth(116)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(8, 12, 8, 12)
        rail_layout.setSpacing(6)
        for title, group in [('NAVIGATE', TOOLS[:2]), ('DRAW & MARK', [entry for entry in TOOLS if entry[0] in DRAWING_TOOLS]), ('FINISH', [entry for entry in TOOLS if entry[0] in ('eraser', 'redact', 'crop')])]:
            heading = QLabel(title)
            heading.setObjectName('railHeading')
            rail_layout.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(4)
            for index, (tool, label, key, tip) in enumerate(group):
                button = tool_button(tool, label, lambda checked=False, t=tool: self.canvas.set_tool(t))
                button.setObjectName('annotationTool')
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                button.setIconSize(QSize(20, 20))
                button.setMinimumSize(46, 45)
                button.setCheckable(True)
                button.setToolTip(f'{label} ({key}) · {tip}')
                self.tools.addButton(button)
                self.tool_buttons[tool] = button
                grid.addWidget(button, index // 2, index % 2)
            rail_layout.addLayout(grid)
        rail_layout.addStretch()
        rail_scroll = QScrollArea()
        rail_scroll.setWidget(self.rail)
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setFixedWidth(118)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rail_scroll = rail_scroll
        workspace.addWidget(rail_scroll)
        self.select_button = self.tool_buttons['select']
        self.select_button.setChecked(True)
        center = QVBoxLayout()
        center.setSpacing(10)
        self.context = QWidget()
        self.context.setObjectName('contextBar')
        controls = QHBoxLayout(self.context)
        controls.setContentsMargins(10, 6, 10, 6)
        controls.setSpacing(8)
        self.tool_name = QLabel('Select')
        self.tool_name.setObjectName('toolName')
        controls.addWidget(self.tool_name)
        self.colour_button = tool_button('pen', 'Colour', self.choose_colour)
        self.colour_palette = ColourPalette(self)
        self.colour_palette.chosen.connect(lambda color: self.change_property('color', color))
        controls.addWidget(self.colour_button)
        self.width_label = QLabel('Size')
        controls.addWidget(self.width_label)
        self.width_control = QSpinBox()
        self.width_control.setRange(1, 80)
        self.width_control.setValue(4)
        self.width_control.setSuffix(' px')
        self.width_control.setMinimumWidth(max(104, self.width_control.fontMetrics().horizontalAdvance('80 px') + 58))
        self.width_control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.width_control.setKeyboardTracking(False)
        self.width_control.setAccessibleName('Drawing size in pixels')
        self.width_control.valueChanged.connect(lambda n: self.change_size('stroke_width', 'width', n))
        controls.addWidget(self.width_control)
        self.size_label = QLabel('Text')
        controls.addWidget(self.size_label)
        self.size_control = QSpinBox()
        self.size_control.setRange(8, 160)
        self.size_control.setValue(24)
        self.size_control.setSuffix(' px')
        self.size_control.setMinimumWidth(max(110, self.size_control.fontMetrics().horizontalAdvance('160 px') + 58))
        self.size_control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.size_control.setKeyboardTracking(False)
        self.size_control.valueChanged.connect(lambda n: self.change_size('font_size', 'font_size', n))
        controls.addWidget(self.size_control)
        self.style_button = tool_button('styles', 'Style', self.choose_style)
        controls.addWidget(self.style_button)
        self.style_popup = StylePopup(self)
        self.style_popup.changed.connect(self.change_property)
        self.style_popup.reset_requested.connect(self.reset_style)
        self.tool_hint = QLabel()
        self.tool_hint.setObjectName('muted')
        self.tool_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        controls.addWidget(self.tool_hint, 1)
        self.undo_button = tool_button('undo', 'Undo (Ctrl+Z)', lambda: self.canvas.doc.undo() if self.canvas.doc else None, icon_only=True)
        self.redo_button = tool_button('redo', 'Redo (Ctrl+Y)', lambda: self.canvas.doc.redo() if self.canvas.doc else None, icon_only=True)
        self.delete_button = tool_button('trash', 'Delete selected annotation', self.canvas.delete_selected, icon_only=True)
        for button in (self.undo_button, self.redo_button, self.delete_button):
            controls.addWidget(button)
        center.addWidget(self.context)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName('editorSplitter')
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
        center.addWidget(self.splitter, 1)
        view_bar = QHBoxLayout()
        self.dimensions = QLabel()
        self.dimensions.setObjectName('muted')
        self.dimensions.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        view_bar.addWidget(self.dimensions, 1)
        self.focus_button = tool_button('focus', 'Focus (Ctrl+Shift+F)', self.toggle_focus, icon_only=True)
        self.focus_button.setCheckable(True)
        view_bar.addWidget(self.focus_button)
        self.button(view_bar, '−', lambda: self.canvas.zoom(1 / 1.2))
        self.zoom_label = QLabel('100%')
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_bar.addWidget(self.zoom_label)
        self.canvas.zoom_changed.connect(lambda n: self.zoom_label.setText(f'{n}%'))
        self.button(view_bar, '+', lambda: self.canvas.zoom(1.2))
        self.button(view_bar, 'Fit', self.canvas.fit_image)
        self.button(view_bar, '1:1', self.canvas.actual_size)
        center.addLayout(view_bar)
        workspace.addLayout(center, 1)
        layout.addLayout(workspace, 1)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.save_status = tool_button('folder', 'Ready to save', self.folder_requested.emit)
        self.save_status.setObjectName('saveStatus')
        self.save_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bottom.addWidget(self.save_status, 1)
        self.ocr_button = tool_button('ocr', 'Extract Text', lambda: self.ocr_requested.emit(None))
        self.ocr_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.ocr_button.setProperty('split', True)
        ocr_menu = QMenu(self)
        self.ocr_area_button = ocr_menu.addAction(icon('capture'), 'Select OCR area', lambda: self.canvas.set_tool('ocr'))
        ocr_menu.addAction('Show extracted text', lambda: self.show_ocr(self.canvas.doc.ocr_text) if self.canvas.doc else None)
        self.ocr_button.setMenu(ocr_menu)
        bottom.addWidget(self.ocr_button)
        more = tool_button('more', 'More')
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction(icon('save'), 'Save As… (Ctrl+Shift+S)', self.save_requested.emit)
        menu.addAction(icon('project'), 'Save Editable Project… (Ctrl+Shift+P)', self.project_requested.emit)
        menu.addAction(icon('library'), 'Save to History', self.history_requested.emit)
        menu.addAction(icon('pin'), 'Pin on Screen', self.pin_requested.emit)
        menu.addSeparator()
        menu.addAction('Select OCR area', lambda: self.canvas.set_tool('ocr'))
        menu.addAction('Show / hide extracted text', self.toggle_ocr)
        menu.addAction('Focus workspace', self.toggle_focus)
        more.setMenu(menu)
        self.more_button = more
        bottom.addWidget(more)
        self.save_button = tool_button('save', 'Save', self.quicksave_requested.emit)
        bottom.addWidget(self.save_button)
        copy = tool_button('copy', 'Copy Image', self.copy_requested.emit)
        copy.setObjectName('primary')
        bottom.addWidget(copy)
        layout.addLayout(bottom)
        self.canvas.area_selected.connect(self.ocr_requested.emit)
        self.canvas.tool_changed.connect(self.tool_changed)
        self.canvas.scene().selectionChanged.connect(self.update_properties)
        shortcuts = [
            ('Ctrl+C', self.copy_requested.emit), ('Ctrl+S', self.quicksave_requested.emit),
            ('Ctrl+Shift+S', self.save_requested.emit),
            ('Ctrl+Shift+P', self.project_requested.emit),
            ('Ctrl+Z', lambda: self.canvas.doc.undo() if self.canvas.doc else None),
            ('Ctrl+Y', lambda: self.canvas.doc.redo() if self.canvas.doc else None),
            ('Ctrl+Shift+Z', lambda: self.canvas.doc.redo() if self.canvas.doc else None),
            ('Ctrl+Shift+F', self.toggle_focus),
            ('Delete', self.canvas.delete_selected), ('Escape', self.escape),
        ]
        shortcuts.extend((key, lambda checked=False, t=tool: self.canvas.set_tool(t)) for tool, label, key, tip in TOOLS)
        for sequence, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        self.tool_changed('select')

    def tool_changed(self, tool):
        if tool in self.tool_buttons:
            self.tool_buttons[tool].setChecked(True)
        else:
            self.tools.setExclusive(False)
            for button in self.tool_buttons.values():
                button.setChecked(False)
            self.tools.setExclusive(True)
        self.update_properties()

    def update_properties(self):
        tool = self.canvas.tool
        index = self.canvas.selected_index()
        selected = self.canvas.doc.annotations[index] if self.canvas.doc and index is not None and index < len(self.canvas.doc.annotations) else None
        kind = selected.kind if tool == 'select' and selected else tool
        names = {entry[0]: entry[1] for entry in TOOLS}
        hints = {entry[0]: entry[3] for entry in TOOLS}
        self.tool_name.setText(names.get(kind, 'OCR area'))
        self.tool_hint.setText(hints.get(kind, 'Drag around the text you want to extract'))
        self.tool_hint.setToolTip(self.tool_hint.text())
        self.colour_button.setVisible(kind in DRAWING_TOOLS)
        self.style_button.setVisible(kind in DRAWING_TOOLS)
        for widget in (self.width_label, self.width_control):
            widget.setVisible(kind in STROKED)
        for widget in (self.size_label, self.size_control):
            widget.setVisible(kind == 'text')
        self.delete_button.setEnabled(selected is not None)
        for widget, value in [(self.width_control, selected.width if selected else self.canvas.stroke_width),
                              (self.size_control, selected.font_size if selected else self.canvas.font_size)]:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.colour_button.setIcon(swatch_icon(selected.color if selected else self.canvas.color))
        if self.style_popup.isVisible() and kind in DRAWING_TOOLS:
            self.style_popup.sync(selected or self.canvas.annotation(kind, []), names.get(kind, kind))

    def toggle_focus(self):
        self.focus_mode = not self.focus_mode
        self.rail_scroll.setVisible(not self.focus_mode)
        self.context.setVisible(not self.focus_mode)
        self.focus_button.setChecked(self.focus_mode)

    def toggle_ocr(self):
        if self.ocr_panel.isHidden() and self.canvas.doc:
            self.show_ocr(self.canvas.doc.ocr_text)
        else:
            self.hide_ocr()

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
        item = self.active_annotation()
        self.colour_palette.display(item.color, self.colour_button)

    def active_annotation(self):
        index = self.canvas.selected_index()
        if self.canvas.tool == 'select' and self.canvas.doc and index is not None:
            return self.canvas.doc.annotations[index]
        return self.canvas.annotation(self.canvas.tool, [])

    def choose_style(self):
        item = self.active_annotation()
        name = dict((entry[0], entry[1]) for entry in TOOLS).get(item.kind, item.kind)
        self.style_popup.display(item, name, self.style_button)

    def change_property(self, key, value):
        item = self.active_annotation()
        if item.kind not in DRAWING_TOOLS:
            return
        if getattr(item, key) == value:
            return
        index = self.canvas.selected_index()
        if self.canvas.tool == 'select' and self.canvas.doc and index is not None:
            updated = deepcopy(item); setattr(updated, key, value)
            self.canvas.doc.replace(index, updated)
        else:
            setattr(self.canvas, 'stroke_width' if key == 'width' else key, value)
            self.canvas.preferences[self.canvas.tool] = self.canvas.current_preferences()
            self.preferences_changed.emit(deepcopy(self.canvas.preferences))
        self.update_properties()

    def reset_style(self):
        item = self.active_annotation()
        if item.kind not in DRAWING_TOOLS:
            return
        values = defaults(item.kind)
        index = self.canvas.selected_index()
        if self.canvas.tool == 'select' and index is not None:
            updated = deepcopy(item)
            for key, value in values.items(): setattr(updated, key, value)
            self.canvas.doc.replace(index, updated)
        else:
            for key, value in values.items(): setattr(self.canvas, 'stroke_width' if key == 'width' else key, value)
            self.canvas.preferences[item.kind] = values
            self.preferences_changed.emit(deepcopy(self.canvas.preferences))
        self.update_properties()

    def load_preferences(self, value):
        self.canvas.preferences = validated_preferences(value)

    def change_size(self, canvas_property, annotation_property, value):
        self.change_property(annotation_property, value)

    def set_document(self, doc):
        if self.canvas.doc:
            self.canvas.doc.changed.disconnect(self.update_state)
        self.canvas.set_document(doc)
        self.ocr_text.blockSignals(True)
        self.ocr_text.clear()
        self.ocr_text.blockSignals(False)
        self.hide_ocr()
        self.escape()
        doc.changed.connect(self.update_state)
        self.update_state()

    def update_state(self):
        doc = self.canvas.doc
        if doc:
            self.undo_button.setEnabled(bool(doc.undo_stack))
            self.redo_button.setEnabled(bool(doc.redo_stack))
            state = 'Unsaved edits' if doc.revision != doc.saved_revision else 'Text not saved to history' if doc.ocr_text != doc.saved_ocr_text else 'Saved'
            self.dimensions.setText(f"{doc.base.width()} × {doc.base.height()} px  ·  {state}")
            self.update_properties()
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
