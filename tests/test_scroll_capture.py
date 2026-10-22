import random
import unittest

from PySide6.QtGui import QColor, QImage, QPainter
from beastsnip.scroll_capture import AlignmentError, ImageStitcher, scroll_offset
from test_document import APP, white_image


def long_image(width=240, height=1600):
    image = white_image(width, height)
    painter, rng = QPainter(image), random.Random(2468)
    for y in range(height):
        for x in range(0, width, 24):
            value = rng.randrange(20, 240)
            painter.fillRect(x, y, 24, 1, QColor(value, value, value))
    painter.end()
    return image


class ScrollStitchTests(unittest.TestCase):
    def test_real_overlapping_pixels_join_to_the_exact_original(self):
        source, stitcher = long_image(), ImageStitcher()
        for y in (0, 170, 390, 600):
            self.assertTrue(stitcher.append(source.copy(0, y, 240, 400)))
        result = stitcher.image()
        self.assertEqual(result.size(), source.copy(0, 0, 240, 1000).size())
        self.assertEqual(result, source.copy(0, 0, 240, 1000))
        self.assertEqual(stitcher.count, 4)

    def test_unchanged_frame_does_not_duplicate_the_bottom(self):
        image, stitcher = long_image(height=400), ImageStitcher()
        self.assertTrue(stitcher.append(image))
        self.assertFalse(stitcher.append(image))
        self.assertEqual(stitcher.height, 400)
        self.assertEqual(stitcher.count, 1)

    def test_uncertain_or_nonoverlapping_frames_leave_previous_result_intact(self):
        source, stitcher = long_image(), ImageStitcher()
        stitcher.append(source.copy(0, 0, 240, 400))
        with self.assertRaises(AlignmentError):
            stitcher.append(source.copy(0, 900, 240, 400))
        self.assertEqual(stitcher.height, 400)
        with self.assertRaises(AlignmentError):
            scroll_offset(white_image(240, 400), white_image(240, 500))

    def test_image_and_height_limits_preserve_the_last_valid_frames(self):
        source, stitcher = long_image(), ImageStitcher(max_pixels=240 * 500)
        stitcher.append(source.copy(0, 0, 240, 400))
        with self.assertRaises(AlignmentError):
            stitcher.append(source.copy(0, 200, 240, 400))
        self.assertEqual(stitcher.count, 1)
        self.assertEqual(stitcher.image(), source.copy(0, 0, 240, 400))
