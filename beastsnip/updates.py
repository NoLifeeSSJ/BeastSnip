"""Explicit update checks, verified downloads and the native Update Centre."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from . import __version__
from .config import atomic_bytes, data_dir

LATEST_URL = 'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/delivery/latest.json'


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', version):
        raise ValueError('The update version is invalid.')
    return tuple(map(int, version.split('.')))


def validate_manifest(value):
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('This update description is not supported.')
    version_tuple(value.get('version'))
    url = urllib.parse.urlparse(value.get('updater_url', ''))
    if url.scheme != 'https' or url.netloc != 'raw.githubusercontent.com' or url.query or url.fragment or not url.path.startswith('/NoLifeeSSJ/BeastSnip/') or not url.path.endswith('/delivery/Update-BeastSnip-' + value['version'] + '.ps1') or '/..' in url.path:
        raise ValueError('The update download address is not supported.')
    if not re.fullmatch('[a-fA-F0-9]{64}', value.get('updater_sha256', '')):
        raise ValueError('The update checksum is missing or invalid.')
    if not isinstance(value.get('notes'), list) or len(value['notes']) > 100 or any(not isinstance(note, str) or len(note) > 4000 for note in value['notes']):
        raise ValueError('The release notes are invalid.')
    return value


def fetch_manifest():
    request = urllib.request.Request(LATEST_URL, headers={'Cache-Control': 'no-cache', 'User-Agent': 'BeastSnip/' + __version__})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('The update description is too large.')
    return validate_manifest(json.loads(raw))


def download_update(manifest, directory):
    validate_manifest(manifest)
    with urllib.request.urlopen(manifest['updater_url'], timeout=60) as response:
        if urllib.parse.urlparse(response.url).netloc != 'raw.githubusercontent.com':
            raise ValueError('The updater redirected outside its expected download source.')
        raw = response.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest().lower() != manifest['updater_sha256'].lower():
        raise ValueError('The downloaded updater failed its SHA256 check. No update was started.')
    path = Path(directory) / ('Update-BeastSnip-' + manifest['version'] + '.ps1')
    atomic_bytes(path, raw)
    return path


def launch_update(path, install_dir):
    if os.name != 'nt':
        raise RuntimeError('Run the PowerShell updater on Windows.')
    return subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(path),
        '-InstallDir', str(install_dir), '-CloseRunningApp', '-Launch'], creationflags=subprocess.CREATE_NEW_CONSOLE)


class UpdateCentre(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.manifest, self.busy = window, None, False
        self.operation_started = 0
        self.update_process = None
        self.setWindowTitle('BeastSnip · Update Centre')
        self.setMinimumSize(480, 400)
        self.resize(660, 540)
        layout = QVBoxLayout(self)
        title = QLabel('Keep BeastSnip up to date')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        layout.addWidget(QLabel('Installed version: ' + __version__))
        self.status = QLabel('Check for releases when you are ready. Updates keep your screenshots and preferences.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setAcceptRichText(False)
        self.notes.setPlaceholderText('Release notes will appear here.')
        layout.addWidget(self.notes, 1)
        note = QLabel('The updater tests a separate candidate first. If activation checks fail, it restores the previous application, Python runtime and settings. Editable recovery is saved before an in-app update when enabled.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        layout.addWidget(note)
        actions = QHBoxLayout()
        history_row = QHBoxLayout()
        history = QPushButton('Version History · all releases')
        history.clicked.connect(window.show_changelog)
        history_row.addWidget(history); history_row.addStretch()
        layout.addLayout(history_row)
        self.check_button = QPushButton('Check for Updates')
        self.check_button.clicked.connect(self.check)
        actions.addWidget(self.check_button)
        self.install_button = QPushButton('Install Update')
        self.install_button.setObjectName('primary')
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install)
        actions.addWidget(self.install_button)
        logs = QPushButton('Update Logs')
        logs.clicked.connect(self.open_logs)
        actions.addWidget(logs)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.poll_status)

    def open_logs(self):
        path = data_dir() / 'update-logs'
        path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.status.setText('The log folder could not be opened: ' + str(path))

    def check(self):
        if self.busy:
            return
        self.busy = True
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.status.setText('Checking GitHub for a release…')
        def completed(result, error):
            self.busy = False
            self.check_button.setEnabled(True)
            if error:
                self.status.setText('Could not check for updates: ' + error)
                return
            self.manifest = result
            newer = version_tuple(result['version']) > version_tuple(__version__)
            self.notes.setPlainText('BeastSnip ' + result['version'] + '\n\n' + '\n\n'.join('• ' + note for note in result['notes']))
            self.status.setText('Version ' + result['version'] + ' is available.' if newer else 'You are up to date.')
            self.install_button.setEnabled(newer and not getattr(sys, 'frozen', False))
            if newer and getattr(sys, 'frozen', False):
                self.status.setText('A new version is available. Use the published PowerShell updater for your source installation; packaged executables need a matching Windows build.')
        self.window.task(fetch_manifest, completed)

    def install(self):
        if self.busy or not self.manifest:
            return
        if not self.window.prepare_update():
            self.status.setText('Finishing saves before the update. Resolve any save error, then choose Install Update again.')
            return
        self.busy = True
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.status.setText('Downloading and verifying the updater…')
        def completed(result, error):
            if not error:
                try:
                    self.operation_started = time.time()
                    self.update_process = launch_update(result, Path(__file__).resolve().parents[1])
                    self.status.setText('Updater started in PowerShell. BeastSnip will restart after the checks pass.')
                    self.poll_timer.start()
                    return
                except Exception as exc:
                    error = str(exc)
            self.busy = False
            self.window.end_update()
            self.check_button.setEnabled(True)
            self.install_button.setEnabled(True)
            self.status.setText('The update did not start: ' + error)
        self.window.task(lambda: download_update(self.manifest, data_dir() / 'updates'), completed)

    def poll_status(self):
        path = data_dir() / 'updates' / 'status.json'
        try:
            if path.stat().st_mtime < self.operation_started:
                self.check_process_exit()
                return
            status = json.loads(path.read_text(encoding='utf-8-sig'))
            self.status.setText(status.get('message', 'Update in progress…'))
            if status.get('state') in ('failed', 'rolled-back', 'complete'):
                self.poll_timer.stop()
                self.busy = False
                self.window.end_update()
                self.check_button.setEnabled(True)
                self.install_button.setEnabled(status['state'] != 'complete')
        except (OSError, ValueError):
            self.check_process_exit()
            return
        if self.busy:
            self.check_process_exit()

    def check_process_exit(self):
        if self.update_process is not None and self.update_process.poll() is not None:
            self.poll_timer.stop()
            self.busy = False
            self.window.end_update()
            self.check_button.setEnabled(True)
            self.install_button.setEnabled(True)
            self.status.setText('PowerShell exited before reporting a completed update. Check Update Logs for the error, then retry.')
