"""Compact colour and drawing-style popovers, with the real stroke renderer."""
from copy import deepcopy

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFormLayout,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QToolButton,
    QScrollArea, QVBoxLayout, QWidget)

from .document import Annotation
from .ui import swatch_icon

DRAWING_TOOLS = {'pen', 'brush', 'highlight', 'line', 'arrow', 'rect', 'round_rect', 'filled', 'ellipse', 'text', 'number'}
FREEHAND = {'pen', 'brush', 'highlight'}
SHAPES = {'rect', 'round_rect', 'filled', 'ellipse'}
STROKED = FREEHAND | {'line', 'arrow'} | SHAPES
ENUMS = {'line_style': ('solid', 'dash', 'dot'), 'cap': ('round', 'square'),
         'fill_style': ('none', 'solid', 'soft'), 'arrow_heads': ('end', 'both', 'none')}


def defaults(tool):
    return dict(color='#f5d45b' if tool == 'highlight' else '#a78bfa',
                width=20 if tool == 'brush' else 4, font_size=24, opacity=100,
                line_style='solid', cap='round', fill_style='solid' if tool == 'filled' else 'none',
                arrow_heads='end', smooth=tool in FREEHAND)


def validated_preferences(value):
    result = {}
    if not isinstance(value, dict):
        return result
    for tool, raw in value.items():
        if tool not in DRAWING_TOOLS or not isinstance(raw, dict):
            continue
        prefs = defaults(tool)
        for key, choices in ENUMS.items():
            if raw.get(key) in choices:
                prefs[key] = raw[key]
        for key, low, high in [('width', 1, 80), ('font_size', 8, 160), ('opacity', 5, 100)]:
            if type(raw.get(key)) is int and low <= raw[key] <= high:
                prefs[key] = raw[key]
        if type(raw.get('smooth')) is bool:
            prefs['smooth'] = raw['smooth']
        color = raw.get('color')
        if isinstance(color, str) and QColor(color).isValid():
            prefs['color'] = QColor(color).name()
        if tool == 'filled' and prefs['fill_style'] == 'none':
            prefs['fill_style'] = 'solid'
        result[tool] = prefs
    return result


def place_popup(popup, anchor):
    available = anchor.screen().availableGeometry()
    popup.setMaximumHeight(max(100, available.height() - 12))
    popup.adjustSize()
    point = anchor.mapToGlobal(anchor.rect().bottomLeft())
    x = max(available.left() + 6, min(point.x(), available.right() - popup.width() - 6))
    y = point.y() + 6
    if y + popup.height() > available.bottom():
        y = max(available.top() + 6, anchor.mapToGlobal(anchor.rect().topLeft()).y() - popup.height() - 6)
    popup.move(x, y)
    popup.show()


class ColourPalette(QWidget):
    chosen = Signal(str)
    COLOURS = ['#a78bfa', '#7355df', '#4d9ff5', '#39b8cd', '#42bc8b', '#f5d45b',
               '#f29a50', '#ed6579', '#f5f6fa', '#b4bac9', '#636d83', '#11141c']
    NAMES = ['Lavender', 'Violet', 'Blue', 'Teal', 'Green', 'Gold', 'Orange', 'Coral', 'White', 'Silver', 'Slate', 'Ink']

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName('drawingPopup')
        self.setMinimumWidth(298)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel('Annotation colour'); title.setObjectName('toolName'); layout.addWidget(title)
        grid = QGridLayout(); grid.setSpacing(8)
        self.swatches = []
        for i, color in enumerate(self.COLOURS):
            button = QToolButton()
            button.setObjectName('colourSwatch')
            button.setIcon(swatch_icon(color))
            button.setIconSize(QSize(24, 24))
            button.setFixedSize(36, 36)
            button.setCheckable(True)
            button.setToolTip(self.NAMES[i] + ' · ' + color.upper())
            button.setAccessibleName(self.NAMES[i] + ' ' + color)
            button.clicked.connect(lambda checked=False, c=color: self.pick(c))
            grid.addWidget(button, i // 6, i % 6)
            self.swatches.append((color, button))
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.hex = QLineEdit(); self.hex.setPlaceholderText('#A78BFA'); self.hex.setMaxLength(7)
        self.hex.setAccessibleName('Hex colour')
        self.hex.returnPressed.connect(self.apply_hex)
        row.addWidget(self.hex)
        apply = QPushButton('Apply'); apply.clicked.connect(self.apply_hex); row.addWidget(apply)
        layout.addLayout(row)
        self.error = QLabel(''); self.error.setWordWrap(True); self.error.hide(); layout.addWidget(self.error)
        custom = QPushButton('More colours…'); custom.clicked.connect(self.custom); layout.addWidget(custom)

    def display(self, color, anchor):
        self.current = color
        self.hex.setText(color.upper()); self.error.clear(); self.error.hide()
        for value, button in self.swatches:
            button.setChecked(value.casefold() == color.casefold())
        place_popup(self, anchor)

    def pick(self, color):
        self.hide()
        self.chosen.emit(color)

    def apply_hex(self):
        text = self.hex.text().strip()
        if len(text) != 7 or not text.startswith('#') or not QColor(text).isValid():
            self.error.setText('Enter a colour such as #A78BFA.'); self.error.show(); return
        self.pick(QColor(text).name())

    def custom(self):
        self.hide()
        color = QColorDialog.getColor(QColor(self.current), self.parentWidget(), 'Annotation colour')
        if color.isValid():
            self.chosen.emit(color.name())


class StrokePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.item = None
        self.setFixedHeight(76)
        self.setMinimumWidth(280)
        self.setAccessibleName('Live drawing style preview')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#eef0f6'))
        painter.setPen(QPen(QColor('#dce0eb'), 1))
        for x in range(0, self.width(), 12):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 12):
            painter.drawLine(0, y, self.width(), y)
        if self.item:
            item = deepcopy(self.item)
            item.offset = QPointF()
            item.width = min(item.width, 24)
            if item.kind == 'highlight': item.width = min(item.width, 6)
            if item.kind in FREEHAND:
                item.points = [QPointF(16 + i * (self.width() - 32) / 7, y) for i, y in enumerate([44, 28, 38, 48, 28, 24, 40, 32])]
            elif item.kind in ('text', 'number'):
                item.points = [QPointF(20, 20 if item.kind == 'text' else 38)]
                item.text, item.font_size = 'Make your point.', 22
            else:
                item.points = [QPointF(24, 20), QPointF(self.width() - 24, 56)]
            item.paint(painter)


class StylePopup(QWidget):
    changed = Signal(str, object)
    reset_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName('drawingPopup')
        self.setMinimumWidth(338)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); self.scroll = scroll
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget(); self.content.setObjectName('drawingPopupContent')
        scroll.setWidget(self.content); outer.addWidget(scroll)
        layout = QVBoxLayout(self.content); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(12)
        self.title = QLabel('Drawing style'); self.title.setObjectName('toolName'); layout.addWidget(self.title)
        self.preview = StrokePreview(); layout.addWidget(self.preview)
        form = QFormLayout(); form.setSpacing(12); layout.addLayout(form)
        self.combos, self.rows = {}, {}
        for key, title, choices in [
            ('line_style', 'Line pattern', [('Solid', 'solid'), ('Dashed', 'dash'), ('Dotted', 'dot')]),
            ('cap', 'Stroke ends', [('Round', 'round'), ('Square', 'square')]),
            ('fill_style', 'Shape fill', [('Outline only', 'none'), ('Solid fill', 'solid'), ('Soft fill', 'soft')]),
            ('arrow_heads', 'Arrowheads', [('End only', 'end'), ('Both ends', 'both'), ('No arrowhead', 'none')])]:
            combo = QComboBox(); combo.setAccessibleName(title)
            for label, value in choices: combo.addItem(label, value)
            combo.currentIndexChanged.connect(lambda index, k=key, c=combo: self.edit(k, c.currentData()))
            label = QLabel(title); label.setBuddy(combo)
            form.addRow(label, combo); self.combos[key] = combo; self.rows[key] = (label, combo)
        opacity_row = QHBoxLayout()
        self.opacity = QSlider(Qt.Orientation.Horizontal); self.opacity.setRange(5, 100); self.opacity.setTracking(False)
        self.opacity.setAccessibleName('Annotation opacity')
        self.opacity_value = QLabel('100%'); self.opacity_value.setMinimumWidth(40)
        self.opacity.sliderMoved.connect(lambda n: self.opacity_value.setText(f'{n}%'))
        self.opacity.valueChanged.connect(lambda n: self.edit('opacity', n))
        opacity_row.addWidget(self.opacity); opacity_row.addWidget(self.opacity_value)
        form.addRow('Opacity', opacity_row)
        self.smoothing = QCheckBox('Smooth freehand strokes')
        self.smoothing.toggled.connect(lambda value: self.edit('smooth', value))
        layout.addWidget(self.smoothing)
        hint = QLabel('Applies to the selected annotation, or the next marks you draw. Each tool remembers its own style.')
        hint.setWordWrap(True); hint.setObjectName('muted'); layout.addWidget(hint)
        reset = QPushButton('Reset this tool'); reset.clicked.connect(self.reset_requested.emit); layout.addWidget(reset)
        self.reset_button = reset

    def sizeHint(self):
        return QSize(350, self.content.sizeHint().height() + 2)

    def display(self, item, name, anchor):
        self.sync(item, name)
        self.scroll.verticalScrollBar().setValue(0)
        place_popup(self, anchor)

    def sync(self, item, name):
        self.item = deepcopy(item)
        self.title.setText(name + ' style')
        for key, combo in self.combos.items():
            value = getattr(item, key)
            if key == 'fill_style' and item.kind == 'filled' and value == 'none': value = 'solid'
            combo.blockSignals(True); combo.setCurrentIndex(combo.findData(value)); combo.blockSignals(False)
            visible = item.kind in STROKED if key == 'line_style' else item.kind in FREEHAND | {'line', 'arrow'} if key == 'cap' else item.kind in SHAPES if key == 'fill_style' else item.kind == 'arrow'
            for widget in self.rows[key]: widget.setVisible(visible)
            if key == 'fill_style':
                combo.model().item(0).setEnabled(item.kind != 'filled')
        self.opacity.blockSignals(True); self.opacity.setValue(item.opacity); self.opacity.blockSignals(False)
        self.opacity_value.setText(f'{item.opacity}%')
        self.smoothing.blockSignals(True); self.smoothing.setChecked(item.smooth); self.smoothing.blockSignals(False)
        self.smoothing.setVisible(item.kind in FREEHAND)
        self.preview.item = item; self.preview.update()

    def edit(self, key, value):
        if not hasattr(self, 'item'): return
        setattr(self.item, key, value)
        if key == 'opacity': self.opacity_value.setText(f'{value}%')
        self.preview.item = self.item; self.preview.update()
        self.changed.emit(key, value)
