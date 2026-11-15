import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pixel_editor import PixelArtDocument


class PixelArtDocumentTests(unittest.TestCase):
    def test_paint_erase_and_clear_preserve_transparency(self):
        art = PixelArtDocument(size=3)
        art.set_pixel(1, 1, "#FF00AA")
        art.set_pixel(2, 1, "#00FF00")
        art.set_pixel(2, 1, None)

        self.assertEqual(art.image.getpixel((1, 1)), (255, 0, 170, 255))
        self.assertEqual(art.image.getpixel((2, 1)), (0, 0, 0, 0))

        art.clear()
        self.assertTrue(all(art.image.getpixel((x, y))[3] == 0 for x in range(3) for y in range(3)))

    def test_saved_art_is_a_transparent_png(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pixel-crosshair.png"
            art = PixelArtDocument(size=2)
            art.set_pixel(0, 1, "#FFFFFF")
            art.save(path)

            with Image.open(path) as saved:
                self.assertEqual(saved.size, (2, 2))
                self.assertEqual(saved.mode, "RGBA")
                self.assertEqual(saved.getpixel((0, 1)), (255, 255, 255, 255))
                self.assertEqual(saved.getpixel((1, 1)), (0, 0, 0, 0))

    def test_out_of_bounds_pixels_are_rejected(self):
        art = PixelArtDocument(size=2)
        with self.assertRaises(IndexError):
            art.set_pixel(2, 0, "#FFFFFF")


if __name__ == "__main__":
    unittest.main()
