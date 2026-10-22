"""Small native UI building blocks and scalable, bundled line icons."""
from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QToolButton, QVBoxLayout)


def gear_path():
    import math
    points = []
    for tooth in range(8):
        for angle, radius in [(-15, 7.7), (-9, 10), (9, 10), (15, 7.7)]:
            radians = math.radians(tooth * 45 + angle)
            points.append(f'{12 + radius * math.cos(radians):.3f},{12 + radius * math.sin(radians):.3f}')
    return '<polygon points="' + ' '.join(points) + '"/><circle cx="12" cy="12" r="3.2"/>'


PATHS = {
    'brush': '<path d="m9 15 9-12 3 3-11 10M9 14c-4-2-6 2-5 4 0 2-2 3-2 3s8 2 9-3c0-2-1-3-2-4z"/>',
    'line': '<path d="M4 20 20 4"/><circle cx="4" cy="20" r="1"/><circle cx="20" cy="4" r="1"/>',
    'round_rect': '<rect x="3" y="5" width="18" height="14" rx="5"/>',
    'eraser': '<path d="m3 14 10-11 8 8-9 10H9zM8 9l8 8M12 21h9"/>',
    'styles': '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    'history': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 12h8M8 17h5"/>',
    'star': '<path d="m12 3 3 6 6 1-4.5 4.5 1 6.5-5.5-3-5.5 3 1-6.5L3 10l6-1z"/>',
    'quick': '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
    'project': '<rect x="3" y="3" width="14" height="14" rx="2"/><path d="M7 7h6M7 11h6M21 7v14H7"/>',
    'recovery': '<path d="M3 10a9 9 0 1 1 2 8M3 3v7h7M12 7v6l4 2"/>',
    'updates': '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    'scroll': '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="m9 8 3-3 3 3m-6 8 3 3 3-3M12 6v12"/>',
    'select': '<path d="m5 3 14 9-7 1-3 7z"/>',
    'pan': '<path d="M7 12V7a2 2 0 0 1 4 0v5-7a2 2 0 0 1 4 0v7-5a2 2 0 0 1 4 0v7c0 5-3 8-7 8-3 0-4-2-6-5l-3-4a2 2 0 0 1 3-2l3 3"/>',
    'pen': '<path d="m4 16 11-11 4 4L8 20H4zM13 7l4 4"/>',
    'highlight': '<path d="m5 13 8-9 7 6-8 9zM5 13l7 6M3 21h12"/>',
    'arrow': '<path d="M4 20 20 4M9 4h11v11"/>',
    'rect': '<rect x="4" y="5" width="16" height="14" rx="2"/>',
    'filled': '<rect x="4" y="5" width="16" height="14" rx="2" fill="currentColor" opacity=".65"/>',
    'ellipse': '<ellipse cx="12" cy="12" rx="9" ry="7"/>',
    'text': '<path d="M4 5h16M12 5v15M8 20h8M4 5v3M20 5v3"/>',
    'number': '<circle cx="12" cy="12" r="9"/><path d="m10 9 2-2v10M9 17h6"/>',
    'redact': '<path d="M12 3 21 7v5c0 5-9 9-9 9s-9-4-9-9V7z"/><path d="M7 12h10" stroke-width="4"/>',
    'crop': '<path d="M6 3v15h15M3 6h15v15"/>',
    'capture': '<path d="M8 3H4v5M16 3h4v5M4 16v5h4M16 21h4v-5M8 12h8M12 8v8"/>',
    'window': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6h1"/>',
    'monitor': '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M12 17v4M8 21h8"/>',
    'copy': '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 5V3H3v13h2"/>',
    'save': '<path d="M4 3h13l4 4v14H4zM8 3v6h9V3M8 21v-8h9v8"/>',
    'folder': '<path d="M3 6h7l2 3h9v11H3z"/>',
    'library': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'undo': '<path d="m8 4-5 5 5 5M3 9h11a7 7 0 0 1 0 14"/>',
    'redo': '<path d="m16 4 5 5-5 5M21 9H10a7 7 0 0 0 0 14"/>',
    'trash': '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    'pin': '<path d="m9 3 12 12-5-1-5 5-1-5-7-7zM10 14l-7 7"/>',
    'ocr': '<path d="M4 8V4h4M16 4h4v4M4 16v4h4M20 16v4h-4M8 8h8M12 8v8M9 16h6"/>',
    'more': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    'search': '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    'settings': gear_path(),
    'focus': '<path d="M9 3H3v6M15 3h6v6M3 15v6h6M21 15v6h-6"/>',
    'check': '<path d="m5 12 4 4L20 5"/>',
    'help': '<circle cx="12" cy="12" r="9"/><path d="M9 8a3 3 0 1 1 5 3l-2 2M12 17h.01"/>',
    'paste': '<path d="M8 5H4v16h16V5h-4M8 3h8v5H8zM8 13h8M8 17h5"/>',
}


def swatch_icon(color):
    result = QIcon()
    for scale in (1, 2, 3):
        pixmap = QPixmap(24 * scale, 24 * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        painter.setPen(QColor('#949bb1'))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(2, 2, 20, 20, 5, 5)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def icon(name, color='#d9dbea'):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" color="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           + PATHS.get(name, PATHS['more']) + '</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for scale in (1, 2, 3):
        pixmap = QPixmap(24 * scale, 24 * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def tool_button(name, text, callback=None, parent=None, icon_only=False):
    button = QToolButton(parent)
    button.setIcon(icon(name))
    button.setIconSize(QSize(20, 20))
    button.setText(text)
    button.setToolTip(text)
    button.setAccessibleName(text)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if icon_only else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        button.clicked.connect(callback)
    return button


class CommandPalette(QDialog):
    def __init__(self, commands, parent):
        super().__init__(parent)
        self.commands = commands
        self.setWindowTitle('BeastSnip · Find an action')
        self.resize(620, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel('What would you like to do?')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search tools, captures, OCR, folders…')
        layout.addWidget(self.search)
        self.results = QListWidget()
        layout.addWidget(self.results, 1)
        hint = QLabel('↑ ↓ to browse    Enter to run    Esc to close')
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.run_selected)
        self.results.itemActivated.connect(self.run_selected)
        self.filter('')
        self.search.setFocus()

    def filter(self, text):
        self.results.clear()
        words = text.casefold().split()
        for index, (name, callback, enabled) in enumerate(self.commands):
            if all(word in name.casefold() for word in words) and enabled():
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.results.addItem(item)
        self.results.setCurrentRow(0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            direction = 1 if event.key() == Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0, min(self.results.count() - 1, self.results.currentRow() + direction)))
            return
        super().keyPressEvent(event)

    def run_selected(self, *args):
        item = self.results.currentItem()
        if item:
            _, callback, enabled = self.commands[item.data(Qt.ItemDataRole.UserRole)]
            if enabled():
                self.accept()
                QTimer.singleShot(0, callback)
