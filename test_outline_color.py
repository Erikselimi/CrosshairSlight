import json
import tempfile
import unittest
from pathlib import Path

from crosshair_data import DEFAULT_OUTLINE_COLOR, PRESETS, Crosshair, ProfileStore, export_cs2_commands, parse_cs2_commands, validate_settings
from crosshair_render import (
    OUTLINE_COLOR,
    build_geometry,
    build_glow_layers,
    contrast_ratio,
    fit_scale,
    glow_layer_colors,
    layer_colors,
    overlay_extent,
)
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


class NeonGlowTests(unittest.TestCase):
    def test_glow_settings_are_validated_and_legacy_settings_keep_glow_off(self):
        settings = validate_settings({
            "glow_enabled": True, "glow_color": "#FF00E6", "glow_size": 12, "glow_strength": 90,
        })
        self.assertEqual((settings.glow_enabled, settings.glow_color, settings.glow_size, settings.glow_strength),
                         (True, "#FF00E6", 12, 90))
        self.assertFalse(validate_settings({"color": "#00FF00"}).glow_enabled)
        for invalid in (
            {"glow_enabled": 1}, {"glow_color": "#GG00FF"},
            {"glow_size": 0}, {"glow_size": 17}, {"glow_strength": -1}, {"glow_strength": 101},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_settings(invalid)

    def test_glow_profiles_round_trip(self):
        settings = Crosshair(glow_enabled=True, glow_color="#FF00E6", glow_size=11, glow_strength=84)
        with tempfile.TemporaryDirectory() as folder:
            store = ProfileStore(Path(folder) / "profiles.json")
            saved = store.save("Neon", settings)
            self.assertEqual(store.get(saved["id"])["settings"]["glow_color"], "#FF00E6")
            self.assertTrue(store.get(saved["id"])["settings"]["glow_enabled"])

    def test_glow_is_a_layered_halo_around_the_fill(self):
        settings = Crosshair(glow_enabled=True, glow_size=6, glow_strength=80)
        fill = build_geometry(settings, 100, 100).fill
        layers = build_glow_layers(fill, settings)
        self.assertEqual(len(layers), 3)
        fill_left = min(rect.x1 for rect in fill)
        self.assertEqual(min(rect.x1 for rect in layers[0][0]), fill_left - 6)
        self.assertGreater(layers[0][1], 0)
        self.assertLess(layers[0][1], layers[1][1])
        self.assertLess(layers[1][1], layers[2][1])
        self.assertEqual(build_glow_layers(fill, Crosshair()), [])

    def test_glow_colors_blend_over_the_preview_backdrop(self):
        settings = Crosshair(glow_enabled=True, glow_color="#00F5FF", glow_strength=100)
        colors = glow_layer_colors(settings, "#101416")
        self.assertEqual(len(colors), 3)
        self.assertEqual(len(set(colors)), 3)
        self.assertTrue(all(color != "#101416" for color in colors))

    def test_glow_fits_in_the_overlay_at_max_size_and_stretch(self):
        settings = Crosshair(
            size=80, vertical_size=80, gap=40, thickness=12, outline=6,
            glow_enabled=True, glow_size=16, glow_strength=100,
        )
        for stretch in ((1.0, 1.0), (1.5, 1.0), (3.0, 3.0)):
            width, height = overlay_extent(stretch)
            center_x, center_y = width // 2, height // 2
            geometry = build_geometry(settings, center_x, center_y, stretch=stretch)
            layers = build_glow_layers(geometry.fill, settings, stretch=stretch)
            rects = geometry.outline + geometry.fill + [rect for layer, _ in layers for rect in layer]
            self.assertGreaterEqual(min(rect.x1 for rect in rects), 0)
            self.assertGreaterEqual(min(rect.y1 for rect in rects), 0)
            self.assertLessEqual(max(rect.x2 for rect in rects), width)
            self.assertLessEqual(max(rect.y2 for rect in rects), height)

    def test_fit_scale_accounts_for_the_glow_radius(self):
        plain = fit_scale(Crosshair(size=20), 30)
        glowing = fit_scale(Crosshair(size=20, glow_enabled=True, glow_size=12), 30)
        self.assertLess(glowing, plain)

    def test_glow_color_is_excluded_from_the_transparency_key(self):
        colors = tuple(glow_layer_colors(Crosshair(glow_enabled=True, glow_color=KEY_COLORS[0])))
        chosen = pick_key_color("#123456", "#654321", colors)
        self.assertNotIn(chosen.upper(), {color.upper() for color in colors})

    def test_cs2_export_explains_that_glow_is_not_exported(self):
        _, warnings = export_cs2_commands(Crosshair(glow_enabled=True))
        self.assertTrue(any("glow was not exported" in warning.lower() for warning in warnings))


if __name__ == "__main__":
    unittest.main()
