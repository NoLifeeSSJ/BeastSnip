import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if os.name != "nt" else "windows")
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect
from beastsnip import windows
from beastsnip.app import MainWindow
from beastsnip.capture import RegionSession
from test_document import APP, white_image


def screen(name, rect, scale=1):
    return SimpleNamespace(name=lambda: name, geometry=lambda: rect, devicePixelRatio=lambda: scale)


class DisplayMappingTests(unittest.TestCase):
    def test_reported_laptop_friendly_name_maps_to_gdi_device_at_150_percent(self):
        qt = screen("NE160QDM-NM9", QRect(0, 0, 1707, 1067), 1.5)
        native = [(r"\\.\DISPLAY1", QRect(0, 0, 2560, 1600))]
        mapped = windows.map_displays([qt], native)
        self.assertEqual(mapped[0].device, r"\\.\DISPLAY1")
        self.assertEqual(mapped[0].physical, native[0][1])

    def test_duplicate_friendly_names_and_reversed_enumeration(self):
        first = screen("DELL", QRect(0, 0, 1707, 1067), 1.5)
        second = screen("DELL", QRect(2560, 0, 1920, 1080), 2)
        native = [(r"\\.\DISPLAY2", QRect(2560, 0, 3840, 2160)),
                  (r"\\.\DISPLAY1", QRect(0, 0, 2560, 1600))]
        mapped = windows.map_displays([first, second], native)
        self.assertEqual([item.device for item in mapped], [r"\\.\DISPLAY1", r"\\.\DISPLAY2"])

    def test_negative_origins_and_mixed_dpi(self):
        qt = screen("External panel", QRect(-1920, -1080, 1280, 720), 1.5)
        mapped = windows.map_displays([qt], [(r"\\.\DISPLAY2", QRect(-1920, -1080, 1920, 1080))])
        self.assertEqual(mapped[0].physical, QRect(-1920, -1080, 1920, 1080))

    def test_existing_gdi_names_still_map_case_insensitively(self):
        qt = screen(r"\\.\display1", QRect(0, 0, 100, 100))
        self.assertEqual(windows.map_displays([qt], [(r"\\.\DISPLAY1", QRect(0, 0, 100, 100))])[0].device, r"\\.\DISPLAY1")

    def test_ambiguous_geometry_is_rejected_instead_of_guessing(self):
        qt = screen("Same model", QRect(0, 0, 100, 100))
        with self.assertRaisesRegex(RuntimeError, "uniquely map"):
            windows.map_displays([qt], [("A", QRect(0, 0, 100, 100)), ("B", QRect(0, 0, 100, 100))])

    def test_picker_retains_native_id_and_monitor_capture_uses_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"BEASTSNIP_DATA_DIR": directory}):
            window = MainWindow(smoke=True)
            qt = screen("NE160QDM-NM9", QRect(0, 0, 1707, 1067), 1.5)
            native = [(r"\\.\DISPLAY1", QRect(0, 0, 2560, 1600))]
            try:
                with patch.object(windows, "IS_WINDOWS", True), patch.object(windows, "monitor_rectangles", return_value=native), patch("beastsnip.app.QApplication.screens", return_value=[qt]):
                    window.refresh_monitors()
                    self.assertEqual(window.monitor.currentData(), r"\\.\DISPLAY1")
                    self.assertIn("NE160QDM-NM9", window.monitor.currentText())
                    window.capture_mode = "monitor"
                    window.capture_monitor = window.monitor.currentData()
                    with patch.object(windows, "grab_pixels", return_value=white_image()) as grab, patch.object(window, "captured") as captured, patch.object(window, "error") as error:
                        window.perform_capture()
                        grab.assert_called_once_with(native[0][1])
                        captured.assert_called_once()
                        error.assert_not_called()
            finally:
                window.integration.close()
                window.history.close()
                window.quitting = True
                window.close()

    def test_region_overlay_uses_the_same_friendly_name_mapping(self):
        qt = screen("NE160QDM-NM9", QRect(0, 0, 100, 100), 1.5)
        native = [(r"\\.\DISPLAY1", QRect(0, 0, 150, 150))]
        with patch.object(windows, "monitor_rectangles", return_value=native), patch.object(windows, "grab_pixels", return_value=white_image(150, 150)), patch("beastsnip.capture.QApplication.screens", return_value=[qt]), patch("beastsnip.capture.RegionOverlay") as overlay:
            session = RegionSession()
            self.assertIs(overlay.call_args.args[1], qt)
            self.assertEqual(overlay.call_args.args[2], native[0][1])
            session.cancel()

    def test_reported_secondary_monitor_maps_with_a_reversed_native_inventory(self):
        primary = screen("Primary panel", QRect(0, 0, 2560, 1440))
        secondary = screen("LEN G25-10", QRect(2560, 0, 1920, 1080))
        native = [(r"\\.\DISPLAY2", QRect(2560, 0, 1920, 1080)),
                  (r"\\.\DISPLAY1", QRect(0, 0, 2560, 1440))]
        with patch.object(windows, "monitor_rectangles", return_value=native), \
             patch.object(windows, "grab_pixels", return_value=white_image(4480, 1440)) as grab, \
             patch("beastsnip.capture.QApplication.screens", return_value=[primary, secondary]), \
             patch("beastsnip.capture.RegionOverlay") as overlay:
            session = RegionSession()
            try:
                grab.assert_called_once_with(QRect(0, 0, 4480, 1440))
                self.assertEqual(session.bounds, QRect(0, 0, 4480, 1440))
                self.assertEqual([call.args[1] for call in overlay.call_args_list], [primary, secondary])
                self.assertEqual([call.args[2] for call in overlay.call_args_list], [native[1][1], native[0][1]])
            finally:
                session.cancel()


if __name__ == "__main__":
    unittest.main()
