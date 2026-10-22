"""Render the actual app with generated examples; never captures the desktop."""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen' if os.name != 'nt' else 'windows')

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from beastsnip.app import MainWindow
from beastsnip.document import Annotation
from beastsnip.updates import UpdateCentre
from beastsnip.ocr import find_tesseract, recognize
from beastsnip.style import STYLE


def sample(title, subtitle, accent):
    image = QImage(1100, 680, QImage.Format.Format_RGB32)
    image.fill(QColor('#f6f8fc'))
    painter = QPainter(image)
    painter.fillRect(0, 0, 12, 680, QColor(accent))
    painter.setPen(QColor('#242c3f'))
    painter.setFont(QFont('DejaVu Sans', 24, QFont.Weight.Bold))
    painter.drawText(60, 85, title)
    painter.setFont(QFont('DejaVu Sans', 16))
    for i, line in enumerate([subtitle, '', '1. Choose New Snip to capture a region.',
                            '2. Use the tools on the left to add context.',
                            '3. Your capture and edits save automatically.', '',
                            'Screenshots stay on your computer.']):
        painter.drawText(60, 155 + i * 54, line)
    painter.end()
    return image


def settle(window):
    for _ in range(500):
        QApplication.processEvents()
        if not window.tasks and not any(s.busy or (s.pending and not s.error) for s in window.autosaves):
            return
        QTest.qWait(10)
    raise RuntimeError('Preview background operations did not finish.')


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    with tempfile.TemporaryDirectory(prefix='beastsnip-preview-') as directory:
        os.environ['BEASTSNIP_DATA_DIR'] = directory
        window = MainWindow(smoke=True)
        window.resize(1440, 940)
        for title, subtitle, accent in [
            ('Keep the useful bit.', 'A detail worth sharing with the team.', '#7aa7cf'),
            ('Make your point.', 'A quick annotation can explain a lot.', '#69bca0'),
            ('Your workspace. A little clearer.', 'Capture a detail, make your point, and keep it close.', '#ab81e8')]:
            window.captured(sample(title, subtitle, accent))
            settle(window)
        window.doc.add(Annotation('arrow', [QPointF(880, 250), QPointF(680, 260)], '#ad7df4', 6))
        settle(window)
        window.show()
        window.editor.canvas.set_tool('arrow')
        window.editor.canvas.fit_image()
        app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-editor.png'))
        text = recognize(window.doc.flatten(), find_tesseract(), 'eng')
        assert 'automatically' in text
        window.doc.ocr_text = text
        window.editor.show_ocr(text)
        window.save_history()
        settle(window)
        app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-ocr.png'))
        window.show_gallery()
        settle(window)
        window.screenshots.item(0).setSelected(True)
        window.screenshots.item(1).setSelected(True)
        window.toggle_favourites()
        settle(window)
        window.date_filter.setCurrentIndex(1)
        settle(window)
        app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-library.png'))
        window.set_quick_capture(True)
        window.captured(sample('Keep capturing.', 'Open, copy or pin from the preview.', '#69bca0'))
        settle(window)
        window.quick_preview.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-quick.png'))
        window.quick_preview.hide()
        centre = UpdateCentre(window)
        centre.notes.setPlainText('BeastSnip 2.1.0\n\n' + '\n\n'.join(line[2:] for line in (ROOT / 'CHANGELOG.md').read_text().split('## 2.1.0 ', 1)[1].split('\n## ', 1)[0].splitlines() if line.startswith('- ')))
        centre.status.setText('BeastSnip 2.1.0 · release notes preview')
        centre.show(); app.processEvents()
        centre.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-updates.png'))
        centre.close()
        window.resize(900, 600); app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1-laptop.png'))
        print('Rendered actual 2.1 workspace, OCR, library, Quick Capture preview, Update Centre and laptop layout.')
        window.shutdown()


if __name__ == '__main__':
    main()
