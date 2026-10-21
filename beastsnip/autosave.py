"""Serial, atomic capture saving. A later edit can never lose to an older write."""
from datetime import datetime
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QTimer, Signal

from .document import save_image


def capture_path(directory):
    return Path(directory) / (datetime.now().strftime('BeastSnip_%Y-%m-%d_%H-%M-%S_%f_') + uuid.uuid4().hex[:8] + '.png')


class AutosaveSession(QObject):
    state_changed = Signal()

    def __init__(self, doc, path, submit, parent=None):
        super().__init__(parent)
        self.doc, self.path, self.submit = doc, Path(path), submit
        self.busy, self.pending, self.error, self.retired = False, True, '', False
        self.observed_revision = doc.revision
        self.written_revision = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.flush)
        doc.changed.connect(self.changed)

    def changed(self):
        if self.doc.revision != self.observed_revision:
            self.observed_revision = self.doc.revision
            self.pending = True
            self.error = ''
            self.timer.start()
            self.state_changed.emit()

    def flush(self):
        self.timer.stop()
        if self.busy or not self.pending:
            return
        revision, image = self.doc.revision, self.doc.flatten()
        self.pending, self.busy, self.error = False, True, ''
        self.state_changed.emit()

        def completed(result, error):
            self.busy = False
            self.error = error
            if error:
                self.pending = True
            else:
                self.written_revision = revision
                if self.doc.revision == revision:
                    self.doc.saved_revision = revision
            self.state_changed.emit()
            if self.pending and not error:
                self.flush()
        self.submit(lambda: save_image(self.path, image), completed)

    def retire(self):
        self.retired = True
        self.doc.changed.disconnect(self.changed)
        self.flush()
