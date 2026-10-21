"""Render the source SVG into Windows ICO and PNG without extra dependencies."""
from pathlib import Path
import struct
import sys

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
app = QGuiApplication.instance() or QGuiApplication(sys.argv)
renderer = QSvgRenderer(str(root / "beastsnip/resources/beastsnip.svg"))
sizes = (16, 24, 32, 48, 64, 128, 256)
images = []
for size in sizes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("PNG icon encoding failed")
    images.append(bytes(data))
    if size == 256:
        image.save(str(root / "beastsnip/resources/beastsnip.png"), "PNG")
offset = 6 + 16 * len(sizes)
entries = []
for size, data in zip(sizes, images):
    entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
(root / "beastsnip/resources/beastsnip.ico").write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries) + b"".join(images))
print("Created BeastSnip ICO (7 sizes) and PNG")
