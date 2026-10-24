import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect
from beastsnip.capture import RegionOverlay, RegionSession
from test_document import APP, white_image


class CoordinateTests(unittest.TestCase):
    def test_negative_coordinates_and_mixed_scale_mapping(self):
        session = SimpleNamespace(frozen=white_image(3840, 2160), bounds=QRect(-1920, -1080, 3840, 2160))
        overlay = RegionOverlay(session, APP.primaryScreen(), QRect(-1920, -1080, 1920, 1080))
        overlay.resize(1280, 720)  # 150% scaling
        result = overlay.native_to_local(QRect(-1770, -930, 300, 150))
        self.assertAlmostEqual(result.x(), 100)
        self.assertAlmostEqual(result.y(), 100)
        self.assertAlmostEqual(result.width(), 200)
        self.assertAlmostEqual(result.height(), 100)
        overlay.close()

    def make_session(self):
        bounds = QRect(-100, -50, 400, 300)
        primary = APP.primaryScreen()
        # Both display inventories must describe the same synthetic desktop.
        # Keep a real QScreen for RegionOverlay's native window, but never let
        # additional monitors on the installer's machine enter this fixture.
        with patch("beastsnip.capture.QApplication.screens", return_value=[primary]), \
             patch("beastsnip.windows.grab_pixels", return_value=white_image(400, 300)), \
             patch("beastsnip.windows.monitor_rectangles", return_value=[(primary.name(), bounds)]):
            return RegionSession()

    def test_synthetic_session_ignores_unrelated_connected_displays(self):
        secondary = SimpleNamespace(name=lambda: "LEN G25-10",
                                    geometry=lambda: QRect(2560, 0, 1920, 1080),
                                    devicePixelRatio=lambda: 1)
        with patch("beastsnip.capture.QApplication.screens", return_value=[APP.primaryScreen(), secondary]):
            session = self.make_session()
        try:
            self.assertEqual(session.bounds, QRect(-100, -50, 400, 300))
            self.assertEqual(len(session.overlays), 1)
            self.assertEqual(session.frozen.size(), session.bounds.size())
        finally:
            session.cancel()

    def test_reverse_drag_returns_expected_frozen_pixels(self):
        session = self.make_session()
        captured = []
        session.captured.connect(captured.append)
        session.start_point = QPoint(100, 100)
        with patch("beastsnip.windows.cursor_position", return_value=QPoint(-50, -25)):
            session.finish()
        self.assertTrue(session.done)
        self.assertEqual((captured[0].width(), captured[0].height()), (150, 125))
        self.assertEqual(session.overlays, [])

    def test_cancel_has_no_capture_and_closes_overlays(self):
        session = self.make_session()
        captured, cancelled = [], []
        session.captured.connect(captured.append)
        session.cancelled.connect(lambda: cancelled.append(True))
        session.cancel()
        session.cancel()  # Idempotent
        self.assertEqual(captured, [])
        self.assertEqual(cancelled, [True])
        self.assertEqual(session.overlays, [])


if __name__ == "__main__":
    unittest.main()
