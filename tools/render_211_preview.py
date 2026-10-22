"""Render 2.1.1 drawing, palette and history using generated sample pixels."""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen' if os.name != 'nt' else 'windows')

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from beastsnip.app import MainWindow
from beastsnip.document import Annotation
from beastsnip.release_history import ReleaseHistory
from beastsnip.style import STYLE
from render_preview import settle


def main():
    app = QApplication.instance() or QApplication([]); app.setStyleSheet(STYLE)
    with tempfile.TemporaryDirectory(prefix='beastsnip-211-preview-') as directory:
        os.environ['BEASTSNIP_DATA_DIR'] = directory
        image = QImage(1100, 720, QImage.Format.Format_ARGB32); image.fill(QColor('#f3f5fa'))
        painter = QPainter(image); painter.setPen(QColor('#27314a'))
        painter.setFont(QFont('DejaVu Sans', 30, QFont.Weight.Bold)); painter.drawText(65, 85, 'A little more expressive.')
        painter.setFont(QFont('DejaVu Sans', 16)); painter.drawText(65, 130, 'Sketch, highlight and explain — with a style that fits.')
        for y, line in [(230, 'Smooth pen and broad brush'), (365, 'Shapes with soft fills'), (530, 'Solid, dashed and dotted lines')]:
            painter.drawText(65, y, line)
        painter.end()
        window = MainWindow(smoke=True); window.resize(1440, 940); window.captured(image); settle(window)
        for annotation in [
            Annotation('pen', [QPointF(520 + i * 65, y) for i, y in enumerate([195, 155, 230, 165, 225, 190, 205])], '#9465d8', 6, smooth=True),
            Annotation('brush', [QPointF(520 + i * 65, y) for i, y in enumerate([275, 250, 280, 255, 265, 250, 260])], '#e68c67', 20, opacity=75, smooth=True),
            Annotation('round_rect', [QPointF(520, 320), QPointF(740, 430)], '#609cbd', 4, fill_style='soft'),
            Annotation('ellipse', [QPointF(790, 320), QPointF(960, 430)], '#6baf97', 4, fill_style='soft'),
            Annotation('line', [QPointF(520, 515), QPointF(960, 515)], '#9465d8', 5, line_style='dash'),
            Annotation('arrow', [QPointF(520, 585), QPointF(960, 585)], '#609cbd', 4, arrow_heads='both'),
        ]: window.doc.add(annotation)
        settle(window); window.show(); window.editor.canvas.set_tool('pen'); app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1.1-drawing.png'))
        window.editor.choose_style(); app.processEvents()
        window.editor.style_popup.grab().save(str(ROOT / 'delivery/BeastSnip-2.1.1-style.png'))
        window.editor.style_popup.hide(); window.editor.choose_colour(); app.processEvents()
        window.editor.colour_palette.grab().save(str(ROOT / 'delivery/BeastSnip-2.1.1-colour.png'))
        window.editor.colour_palette.hide()
        window.resize(900, 600); app.processEvents()
        window.grab().save(str(ROOT / 'delivery/BeastSnip-2.1.1-laptop.png'))
        history = ReleaseHistory(window); history.show(); app.processEvents()
        history.grab().save(str(ROOT / 'delivery/BeastSnip-2.1.1-history.png'))
        history.close(); window.shutdown()
        print('Rendered actual 2.1.1 drawing workspace, style preview, colour palette, laptop layout and version history.')


if __name__ == '__main__': main()
