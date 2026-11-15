import itertools
import unittest

from crosshair_data import PRESETS, Crosshair
from crosshair_render import (
    OVERLAY_SIZE,
    blend_color,
    build_geometry,
    fit_scale,
    overlay_extent,
    parse_resolution,
    stretch_factors,
)


def pixels(rects):
    return {(x, y) for rect in rects for x in range(rect.x1, rect.x2) for y in range(rect.y1, rect.y2)}


def mirror_x(points, geometry):
    return {(int(2 * geometry.center[0] - 1 - x), y) for x, y in points}


def mirror_y(points, geometry):
    return {(x, int(2 * geometry.center[1] - 1 - y)) for x, y in points}


SIZES = [(80, 80), (1, 1), (24, 17), (5, 40)]
CANVASES = [(400, 300), (401, 301), (400, 301), (401, 300), (333, 222)]


class RenderGeometryTests(unittest.TestCase):
    def test_every_shape_is_mirror_symmetric_for_all_dimensions(self):
        for shape, (size, vertical), gap, thickness, outline, dot in itertools.product(
            ("Cross", "T", "Dot", "Circle"), SIZES, (0, 1, 2, 7, 40), (1, 2, 3, 6, 12), (0, 1, 2, 6), (False, True)
        ):
            settings = Crosshair(shape=shape, size=size, vertical_size=vertical, gap=gap, thickness=thickness,
                                 outline=outline, center_dot=dot, dot_size=5)
            geometry = build_geometry(settings, 200, 150)
            label = f"{shape} {size}x{vertical} gap{gap} t{thickness} o{outline} dot{dot}"
            for name, layer in (("fill", geometry.fill), ("outline", geometry.outline)):
                points = pixels(layer)
                self.assertEqual(points, mirror_x(points, geometry), f"{label}: {name} not left/right symmetric")
                if shape != "T":
                    self.assertEqual(points, mirror_y(points, geometry), f"{label}: {name} not top/bottom symmetric")

    def test_opposite_arms_have_matching_dimensions(self):
        for gap, thickness in itertools.product((1, 3, 10), (1, 2, 3, 4, 5)):
            settings = Crosshair(size=20, vertical_size=14, gap=gap, thickness=thickness, center_dot=False)
            arms = build_geometry(settings, 100, 100).fill
            horizontal = sorted((r for r in arms if r.height == thickness and r.width == 20), key=lambda r: r.x1)
            vertical = sorted((r for r in arms if r.width == thickness and r.height == 14), key=lambda r: r.y1)
            self.assertEqual(len(horizontal), 2)
            self.assertEqual(len(vertical), 2)
            self.assertEqual(horizontal[0].width, horizontal[1].width)
            self.assertEqual(vertical[0].height, vertical[1].height)

    def test_center_matches_preview_center_for_odd_and_even_canvases(self):
        for (width, height), thickness in itertools.product(CANVASES, (1, 2, 3, 4)):
            settings = Crosshair(thickness=thickness)
            geometry = build_geometry(settings, width // 2, height // 2)
            self.assertLessEqual(abs(geometry.center[0] - width / 2), 0.5)
            self.assertLessEqual(abs(geometry.center[1] - height / 2), 0.5)

    def test_resizing_only_translates_the_design(self):
        settings = Crosshair(size=22, gap=4, thickness=3, outline=2)

        def normalized(width, height):
            geometry = build_geometry(settings, width // 2, height // 2)
            return {(x - width // 2, y - height // 2) for x, y in pixels(geometry.fill)}, \
                   {(x - width // 2, y - height // 2) for x, y in pixels(geometry.outline)}

        reference = normalized(400, 300)
        for width, height in CANVASES:
            self.assertEqual(normalized(width, height), reference)

    def test_color_and_opacity_do_not_change_geometry(self):
        base = build_geometry(Crosshair(), 100, 100)
        other = build_geometry(Crosshair(color="#123456", opacity=10), 100, 100)
        self.assertEqual(base.fill, other.fill)
        self.assertEqual(base.outline, other.outline)

    def test_gap_leaves_the_center_clear_and_outline_does_not_fill_it(self):
        for gap, thickness, outline in itertools.product((2, 3, 5, 9), (1, 2, 3, 5), (1, 2)):
            if gap <= outline:
                continue  # an outline as wide as the gap legitimately fills it
            settings = Crosshair(gap=gap, thickness=thickness, outline=outline, center_dot=False)
            geometry = build_geometry(settings, 100, 100)
            painted = pixels(geometry.fill) | pixels(geometry.outline)
            self.assertNotIn((100, 100), painted, f"dark patch at center: gap{gap} t{thickness} o{outline}")

    def test_zero_gap_is_one_continuous_cross(self):
        for thickness in (1, 2, 3, 4):
            settings = Crosshair(gap=0, thickness=thickness, center_dot=False)
            geometry = build_geometry(settings, 100, 100)
            self.assertIn((100, 100), pixels(geometry.fill))
            self.assertEqual(len(geometry.fill), 2)

    def test_outline_surrounds_the_fill(self):
        for settings in (Crosshair(), Crosshair(outline=3, gap=0), Crosshair(shape="Dot", size=10),
                         Crosshair(shape="Circle", size=30, vertical_size=20, gap=0)):
            geometry = build_geometry(settings, 100, 100)
            self.assertTrue(pixels(geometry.fill) <= pixels(geometry.outline))
            self.assertTrue(pixels(geometry.outline) - pixels(geometry.fill))

    def test_outline_disabled_draws_no_outline(self):
        geometry = build_geometry(Crosshair(outline=0), 100, 100)
        self.assertEqual(geometry.outline, [])

    def test_dot_only_and_ring_shapes(self):
        dot = build_geometry(Crosshair(shape="Dot", size=9, outline=0), 100, 100)
        self.assertIn((100, 100), pixels(dot.fill))
        ring = build_geometry(Crosshair(shape="Circle", size=40, vertical_size=40, thickness=3, outline=0), 100, 100)
        self.assertNotIn((100, 100), pixels(ring.fill))
        self.assertIn((100, 80), pixels(ring.fill))

    def test_t_shape_has_no_top_arm(self):
        geometry = build_geometry(Crosshair(shape="T", gap=3, center_dot=False, outline=0), 100, 100)
        self.assertEqual(len(geometry.fill), 3)
        self.assertTrue(all(rect.y1 >= 100 - 2 or rect.height <= 3 for rect in geometry.fill))
        self.assertFalse(any(y < 100 - 3 for _x, y in pixels(geometry.fill)))

    def test_largest_possible_design_fits_in_the_overlay(self):
        half = OVERLAY_SIZE // 2
        worst = (
            Crosshair(size=80, vertical_size=80, gap=40, thickness=12, outline=6),
            Crosshair(shape="Circle", size=80, vertical_size=80, thickness=12, outline=6),
            Crosshair(shape="Dot", size=80, outline=6),
            Crosshair(size=80, vertical_size=80, gap=40, thickness=12, outline=6, dot_size=20),
        )
        for settings in worst:
            bounds = build_geometry(settings, half, half).bounds()
            self.assertGreaterEqual(bounds.x1, 0)
            self.assertGreaterEqual(bounds.y1, 0)
            self.assertLessEqual(bounds.x2, OVERLAY_SIZE)
            self.assertLessEqual(bounds.y2, OVERLAY_SIZE)

    def test_zoom_scales_every_dimension_consistently(self):
        for scale in (0.5, 1.0, 1.5, 2.0):
            geometry = build_geometry(Crosshair(), 300, 300, scale)
            for name in ("fill", "outline"):
                points = pixels(getattr(geometry, name))
                self.assertEqual(points, mirror_x(points, geometry))
                self.assertEqual(points, mirror_y(points, geometry))

    def test_all_presets_render_symmetrically(self):
        for name, preset in PRESETS.items():
            geometry = build_geometry(preset, 150, 150)
            points = pixels(geometry.fill)
            self.assertTrue(points, name)
            self.assertEqual(points, mirror_x(points, geometry), name)

    def test_fit_scale_and_blend(self):
        self.assertEqual(fit_scale(Crosshair(size=10, gap=0), 100), 1.0)
        self.assertLess(fit_scale(Crosshair(size=80, gap=40), 36), 1.0)
        self.assertEqual(blend_color("#FFFFFF", "#000000", 100), "#FFFFFF")
        self.assertEqual(blend_color("#FFFFFF", "#000000", 0), "#000000")


STRETCHES = [(1920 / 1720, 1.0), (1.5, 1.0), (1920 / 1280, 1080 / 960), (3.0, 3.0), (1.0, 2.0), (0.5, 0.75)]


class StretchTests(unittest.TestCase):
    def test_no_stretch_is_identical_to_the_default(self):
        for preset in PRESETS.values():
            plain = build_geometry(preset, 150, 150)
            neutral = build_geometry(preset, 150, 150, 1.0, (1.0, 1.0))
            self.assertEqual(plain.fill, neutral.fill)
            self.assertEqual(plain.outline, neutral.outline)

    def test_every_shape_stays_mirror_symmetric_when_stretched(self):
        for shape, stretch, gap, thickness, outline, dot in itertools.product(
            ("Cross", "T", "Dot", "Circle"), STRETCHES, (0, 3, 9), (1, 2, 3, 5), (0, 1, 2), (False, True)
        ):
            settings = Crosshair(shape=shape, size=18, vertical_size=14, gap=gap, thickness=thickness,
                                 outline=outline, center_dot=dot, dot_size=4)
            geometry = build_geometry(settings, 300, 300, 1.0, stretch)
            label = f"{shape} stretch{stretch} gap{gap} t{thickness} o{outline} dot{dot}"
            for name, layer in (("fill", geometry.fill), ("outline", geometry.outline)):
                points = pixels(layer)
                self.assertEqual(points, mirror_x(points, geometry), f"{label}: {name} not left/right symmetric")
                if shape != "T":
                    self.assertEqual(points, mirror_y(points, geometry), f"{label}: {name} not top/bottom symmetric")

    def test_horizontal_stretch_widens_only_horizontal_measurements(self):
        settings = Crosshair(size=20, vertical_size=20, gap=4, thickness=2, outline=0, center_dot=False)
        arms = build_geometry(settings, 200, 200, 1.0, (1.5, 1.0)).fill
        horizontal = [rect for rect in arms if rect.width > rect.height]
        vertical = [rect for rect in arms if rect.height > rect.width]
        self.assertEqual(len(horizontal), 2)
        self.assertEqual(len(vertical), 2)
        for rect in horizontal:
            self.assertEqual((rect.width, rect.height), (30, 2))  # length 20 -> 30, thickness unchanged
        for rect in vertical:
            self.assertEqual((rect.width, rect.height), (3, 20))  # width 2 -> 3, length unchanged
        # The gap is widened the same way: 4 -> 6 pixels on each side of the center. The vertical arm is
        # now an odd 3 px wide, so there is also one center pixel column: 6 + 1 + 6 = 13.
        left, right = sorted(horizontal, key=lambda rect: rect.x1)
        self.assertEqual(right.x1 - left.x2, 13)

    def test_stretched_dot_is_a_wider_ellipse(self):
        geometry = build_geometry(Crosshair(shape="Dot", size=10, outline=0), 100, 100, 1.0, (2.0, 1.0))
        box = geometry.bounds()
        self.assertEqual((box.width, box.height), (20, 10))

    def test_stretch_combines_with_zoom(self):
        zoomed = build_geometry(Crosshair(), 200, 200, 2.0, (1.0, 1.0))
        stretched = build_geometry(Crosshair(), 200, 200, 1.0, (2.0, 2.0))
        self.assertEqual(zoomed.fill, stretched.fill)

    def test_largest_stretched_design_fits_in_the_overlay(self):
        worst = (
            Crosshair(size=80, vertical_size=80, gap=40, thickness=12, outline=6),
            Crosshair(shape="Circle", size=80, vertical_size=80, thickness=12, outline=6),
            Crosshair(shape="Dot", size=80, outline=6),
            Crosshair(size=80, vertical_size=80, gap=40, thickness=12, outline=6, dot_size=20),
            Crosshair(shape="T", size=80, vertical_size=80, gap=40, thickness=11, outline=6),
        )
        for stretch in STRETCHES + [(0.25, 0.25), (3.0, 1.0), (1.0, 3.0)]:
            width, height = overlay_extent(stretch)
            self.assertEqual((width % 2, height % 2), (0, 0))
            for settings in worst:
                bounds = build_geometry(settings, width // 2, height // 2, 1.0, stretch).bounds()
                self.assertGreaterEqual(bounds.x1, 0, f"{stretch} {settings.shape}")
                self.assertGreaterEqual(bounds.y1, 0, f"{stretch} {settings.shape}")
                self.assertLessEqual(bounds.x2, width, f"{stretch} {settings.shape}")
                self.assertLessEqual(bounds.y2, height, f"{stretch} {settings.shape}")

    def test_unstretched_overlay_matches_the_original_size(self):
        self.assertEqual(overlay_extent(), (OVERLAY_SIZE, OVERLAY_SIZE))

    def test_parse_resolution(self):
        self.assertEqual(parse_resolution("1720x1080"), (1720, 1080))
        self.assertEqual(parse_resolution(" 1720 X 1080 "), (1720, 1080))
        self.assertEqual(parse_resolution("1720×1080"), (1720, 1080))
        for off in ("", "Off", "off (native)", "Native"):
            self.assertIsNone(parse_resolution(off))
        for bad in ("1720", "wide", "1720x", "100x100", "9000x9000", "1720-1080"):
            with self.assertRaises(ValueError, msg=bad):
                parse_resolution(bad)

    def test_stretch_factors(self):
        self.assertEqual(stretch_factors((1920, 1080), None), (1.0, 1.0))
        factor_x, factor_y = stretch_factors((1920, 1080), (1720, 1080))
        self.assertAlmostEqual(factor_x, 1920 / 1720)
        self.assertEqual(factor_y, 1.0)
        # Windows itself already runs at the game's resolution: nothing more to stretch.
        self.assertEqual(stretch_factors((1720, 1080), (1720, 1080)), (1.0, 1.0))
        # Extreme values are clamped so the overlay window stays a sensible size.
        self.assertEqual(stretch_factors((7680, 4320), (640, 480)), (3.0, 3.0))
        self.assertEqual(stretch_factors((640, 480), (7680, 4320)), (0.25, 0.25))

    def test_fit_scale_accounts_for_stretch(self):
        settings = Crosshair(size=40, gap=10)
        self.assertLess(fit_scale(settings, 60, (2.0, 1.0)), fit_scale(settings, 60))


if __name__ == "__main__":
    unittest.main()