import itertools
import unittest

from crosshair_data import PRESETS, Crosshair
from crosshair_render import OVERLAY_SIZE, blend_color, build_geometry, fit_scale


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


if __name__ == "__main__":
    unittest.main()
