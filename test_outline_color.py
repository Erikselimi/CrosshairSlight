import json
import tempfile
import unittest
from pathlib import Path

from crosshair_data import DEFAULT_OUTLINE_COLOR, PRESETS, Crosshair, ProfileStore, export_cs2_commands, parse_cs2_commands, validate_settings
from crosshair_render import OUTLINE_COLOR, build_geometry, contrast_ratio, layer_colors
from overlay import KEY_COLORS, pick_key_color


class OutlineColorDataTests(unittest.TestCase):
    def test_default_outline_color_is_the_classic_dark_border(self):
        self.assertEqual(Crosshair().outline_color, DEFAULT_OUTLINE_COLOR)
        self.assertEqual(OUTLINE_COLOR, DEFAULT_OUTLINE_COLOR)

    def test_outline_color_is_validated(self):
        self.assertEqual(validate_settings({"outline_color": "#ff00aa"}).outline_color, "#ff00aa")
        for invalid in ("ff00aa", "#FF00", "#GG0000", 5, None):
            with self.assertRaises(ValueError, msg=repr(invalid)):
                validate_settings({"outline_color": invalid})

    def test_older_settings_default_to_the_classic_outline(self):
        self.assertEqual(validate_settings({"color": "#00FF00"}).outline_color, DEFAULT_OUTLINE_COLOR)
        self.assertEqual(validate_settings(Crosshair(color="#00FF00")).outline_color, DEFAULT_OUTLINE_COLOR)

    def test_every_preset_has_a_valid_outline_color(self):
        for name, preset in PRESETS.items():
            self.assertEqual(validate_settings(preset).shape, preset.shape, name)
            self.assertRegex(preset.outline_color, r"^#[0-9A-Fa-f]{6}$", name)

    def test_settings_round_trip_keeps_the_outline_color(self):
        settings = validate_settings({"color": "#E8FF45", "outline_color": "#FF00E6", "outline": 2})
        self.assertEqual(validate_settings(settings).outline_color, "#FF00E6")


class OutlineColorRenderTests(unittest.TestCase):
    def test_outline_color_does_not_change_geometry(self):
        base = build_geometry(Crosshair(outline_color="#101416"), 100, 100)
        other = build_geometry(Crosshair(outline_color="#FF00E6"), 100, 100)
        self.assertEqual(base.fill, other.fill)
        self.assertEqual(base.outline, other.outline)

    def test_layer_colors_use_the_outline_color(self):
        settings = Crosshair(color="#FF0000", outline_color="#0000FF", opacity=100)
        self.assertEqual(layer_colors(settings), ("#0000FF", "#FF0000"))

    def test_outline_can_be_brighter_than_the_fill(self):
        settings = Crosshair(color="#101416", outline_color="#FFFFFF", opacity=100)
        self.assertEqual(layer_colors(settings), ("#FFFFFF", "#101416"))

    def test_layer_colors_blend_both_layers_for_the_preview(self):
        settings = Crosshair(color="#FF0000", outline_color="#0000FF", opacity=50)
        self.assertEqual(layer_colors(settings, "#FFFFFF"), ("#8080FF", "#FF8080"))

    def test_contrast_ratio(self):
        self.assertEqual(contrast_ratio("#000000", "#FFFFFF"), contrast_ratio("#FFFFFF", "#000000"))
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(contrast_ratio("#101416", "#101416"), 1.0, places=6)
        self.assertGreater(contrast_ratio("#101416", "#E8FF45"), contrast_ratio("#101416", "#303030"))


class OutlineColorProfileTests(unittest.TestCase):
    def test_profiles_and_json_keep_the_outline_color(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProfileStore(Path(folder) / "profiles.json")
            saved = store.save("Neon", Crosshair(outline=2, outline_color="#FF00E6"))
            self.assertEqual(saved["settings"]["outline_color"], "#FF00E6")
            self.assertEqual(store.get(saved["id"])["settings"]["outline_color"], "#FF00E6")
            destination = Path(folder) / "profile.json"
            store.export_profile(saved["id"], destination)
            imported = store.import_profile(destination)
            self.assertEqual(imported["settings"]["outline_color"], "#FF00E6")

    def test_older_profile_json_loads_with_the_classic_outline(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "legacy.json"
            destination.write_text(json.dumps({"name": "Legacy", "settings": {"color": "#00FF00"}}), encoding="utf-8")
            store = ProfileStore(Path(folder) / "profiles.json")
            imported = store.import_profile(destination)
            self.assertEqual(imported["settings"]["outline_color"], DEFAULT_OUTLINE_COLOR)


class OutlineColorOverlayTests(unittest.TestCase):
    def test_key_color_never_matches_the_fill_or_the_outline(self):
        for key in KEY_COLORS:
            self.assertNotEqual(pick_key_color(key, "#123456").upper(), key.upper())
            self.assertNotEqual(pick_key_color("#123456", key).upper(), key.upper())
            self.assertIn(pick_key_color(key, key), KEY_COLORS)

    def test_key_color_is_stable_for_ordinary_colors(self):
        self.assertEqual(pick_key_color("#E8FF45", "#101416"), pick_key_color("#E8FF45", "#101416"))


class OutlineColorGameConfigTests(unittest.TestCase):
    def test_custom_outline_color_is_reported_for_cs2(self):
        _, warnings = export_cs2_commands(Crosshair(outline=2, outline_color="#FF00E6"))
        self.assertTrue(any("outline color" in warning.lower() for warning in warnings))

    def test_classic_outline_color_needs_no_warning(self):
        _, warnings = export_cs2_commands(Crosshair(outline=2))
        self.assertFalse(any("outline color" in warning.lower() for warning in warnings))

    def test_cs2_import_uses_the_classic_outline_color(self):
        imported = parse_cs2_commands("cl_crosshairsize 5\ncl_crosshair_outlinethickness 2")
        self.assertEqual(imported.settings.outline_color, DEFAULT_OUTLINE_COLOR)


if __name__ == "__main__":
    unittest.main()
