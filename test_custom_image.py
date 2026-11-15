import tempfile
import unittest
from pathlib import Path

from PIL import Image

from crosshair_data import Crosshair, ProfileStore, validate_settings
from crosshair_render import _centered_image_position, _remove_background, _scaled_image_size


class CustomImageSettingsTests(unittest.TestCase):
    def test_image_settings_round_trip_in_profiles_and_json(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "crosshair.png"
            image_path.write_bytes(b"image placeholder")
            store = ProfileStore(Path(folder) / "profiles.json")
            settings = Crosshair(
                shape="Image",
                image_path=str(image_path),
                image_scale=175,
                remove_background=True,
                bg_tolerance=42,
            )

            saved = store.save("Custom image", settings)
            self.assertEqual(saved["settings"]["image_path"], str(image_path))
            self.assertEqual(saved["settings"]["image_scale"], 175)
            self.assertTrue(saved["settings"]["remove_background"])
            self.assertEqual(saved["settings"]["bg_tolerance"], 42)

            destination = Path(folder) / "custom.json"
            store.export_profile(saved["id"], destination)
            imported = store.import_profile(destination)
            self.assertEqual(imported["settings"], saved["settings"])

    def test_image_settings_require_a_png_or_jpg_file(self):
        with tempfile.TemporaryDirectory() as folder:
            invalid_path = Path(folder) / "crosshair.tiff"
            invalid_path.touch()
            with self.assertRaisesRegex(ValueError, "PNG, JPG"):
                validate_settings(Crosshair(shape="Image", image_path=str(invalid_path)))

    def test_background_removal_uses_top_left_rgb_and_tolerance(self):
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 0, 0, 255), (10, 0, 0, 255), (11, 0, 0, 255)])

        result = _remove_background(image, 10)

        self.assertEqual(
            [result.getpixel((x, 0)) for x in range(3)],
            [(0, 0, 0, 0), (10, 0, 0, 0), (11, 0, 0, 255)],
        )

    def test_image_dimensions_apply_scale_and_stretch_independently(self):
        self.assertEqual(_scaled_image_size(80, 40, 150, 1.0, (1.5, 1.0)), (180, 60))
        self.assertEqual(_centered_image_position(500, 300, 180, 60), (410, 270))


if __name__ == "__main__":
    unittest.main()
