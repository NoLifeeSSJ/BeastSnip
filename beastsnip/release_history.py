"""Offline, version-separated release history generated from CHANGELOG.md."""
import html
import json
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from . import __version__
from .changelog import parse_changelog
from .config import resource



def load_history():
    value = json.loads(resource('changelog.json').read_text(encoding='utf-8'))
    if value.get('schema') != 1 or not isinstance(value.get('releases'), list):
        raise ValueError('The local version history could not be read.')
    return value['releases']


def release_text(release):
    lines = ['BeastSnip ' + release['version'] + ' · ' + release['date']]
    for section in release['sections']:
        lines.extend(['', section['title'], *['• ' + item for item in section['items']]])
    return '\n'.join(lines)


def release_html(release):
    esc = html.escape
    current = ' · Installed version' if release['version'] == __version__ else ''
    parts = [f'<h2>BeastSnip {esc(release["version"])}</h2>', f'<p style="color:#aeb9d0">{esc(release["date"] + current)}</p>']
    for section in release['sections']:
        parts.append('<h3>' + esc(section['title']) + '</h3><ul>')
        for item in section['items']:
            # Keep local Markdown filenames readable, without enabling HTML.
            item = esc(item)
            item = re.sub(r'`([^`]+)`', r'<code>\1</code>', item)
            parts.append('<li style="margin-bottom:10px">' + item + '</li>')
        parts.append('</ul>')
    return ''.join(parts)


class ReleaseHistory(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.releases = load_history()
        self.setWindowTitle('BeastSnip · Version history')
        self.setMinimumSize(660, 420); self.resize(920, 680)
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        heading = QLabel('Every BeastSnip update'); heading.setObjectName('sectionTitle'); layout.addWidget(heading)
        detail = QLabel(f'{len(self.releases)} releases · Select a version or search across the complete history. Available offline.')
        detail.setWordWrap(True); detail.setObjectName('muted'); layout.addWidget(detail)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search versions, features or fixes…')
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.filter); layout.addWidget(self.search)
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False)
        self.versions = QListWidget(); self.versions.setMinimumWidth(170)
        self.versions.currentItemChanged.connect(self.display); splitter.addWidget(self.versions)
        self.reader = QTextBrowser(); self.reader.setOpenExternalLinks(False); self.reader.setMinimumWidth(300)
        self.reader.setStyleSheet('QTextBrowser { background:#141924; border:1px solid #343b50; border-radius:10px; padding:16px; font-size:14px; }')
        splitter.addWidget(self.reader); splitter.setSizes([210, 650]); layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.copy = QPushButton('Copy shown notes'); self.copy.clicked.connect(self.copy_notes); actions.addWidget(self.copy)
        actions.addStretch(); close = QPushButton('Close'); close.clicked.connect(self.close); actions.addWidget(close)
        layout.addLayout(actions)
        self.filter('')

    def filter(self, text):
        previous = self.versions.currentItem()
        version = previous.data(Qt.ItemDataRole.UserRole) if previous else __version__
        words = text.casefold().split()
        self.matches = [r for r in self.releases if all(w in release_text(r).casefold() for w in words)]
        self.versions.blockSignals(True); self.versions.clear()
        if self.matches:
            all_versions = QListWidgetItem('All matching releases' if words else 'All releases')
            all_versions.setData(Qt.ItemDataRole.UserRole, '*'); self.versions.addItem(all_versions)
            for release in self.matches:
                item = QListWidgetItem(release['version'] + (' · Current' if release['version'] == __version__ else '') + '\n' + release['date'])
                item.setData(Qt.ItemDataRole.UserRole, release['version']); self.versions.addItem(item)
            index = next((i for i in range(self.versions.count()) if self.versions.item(i).data(Qt.ItemDataRole.UserRole) == version), 1)
            self.versions.setCurrentRow(index)
        self.versions.blockSignals(False); self.display()

    def display(self, *args):
        item = self.versions.currentItem()
        version = item.data(Qt.ItemDataRole.UserRole) if item else None
        shown = self.matches if version == '*' else [r for r in self.matches if r['version'] == version]
        self.shown_text = '\n\n' + ('\n\n' + '─' * 40 + '\n\n').join(release_text(r) for r in shown)
        self.reader.setHtml('<body style="color:#e4e7f1;font-family:Segoe UI,sans-serif">' + '<hr style="color:#454d64">'.join(release_html(r) for r in shown) + '</body>' if shown else '<p>No matching releases. Try another search.</p>')
        self.reader.verticalScrollBar().setValue(0); self.copy.setEnabled(bool(shown))

    def copy_notes(self):
        QApplication.clipboard().setText(self.shown_text.strip())
