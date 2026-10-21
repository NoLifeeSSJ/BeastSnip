import logging
from PySide6.QtCore import QObject, QRunnable, Signal


class TaskSignals(QObject):
    finished = Signal(object, str)


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.function(), "")
        except Exception as error:
            logging.error("Background operation failed (%s)", type(error).__name__)
            self.signals.finished.emit(None, str(error))
