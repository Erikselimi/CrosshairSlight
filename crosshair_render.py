"""Pixel-exact crosshair geometry.

This module is deliberately free of any UI code. ``build_geometry`` turns crosshair settings into
lists of integer rectangles (half-open: x1/y1 inclusive, x2/y2 exclusive), and ``draw_on_canvas``
paints those rectangles into a Tk ``PhotoImage`` so that every pixel lands exactly where the
geometry says it should.

Meaning of the settings
-----------------------
size / vertical_size  Length of each horizontal / vertical arm, NOT counting the gap.
gap                   Empty space between the crosshair center and the inner end of each arm.
thickness             Height of horizontal arms and width of vertical arms.
outline / outline_color
                      Extra border added around every arm (and the dot), in its own color.
center_dot / dot_size Optional dot (diameter) in the middle of a Cross.
Dot shape             ``size`` is the diameter.
Circle shape          ``size`` / ``vertical_size`` are the outer diameters; ``thickness`` is the ring width.

Centering
---------
The caller passes one integer pixel ``(center_x, center_y)`` (normally ``width // 2``). A bar of odd
thickness is centered on that pixel; a bar of even thickness is centered on the boundary to its left /
above. Opposite arms are always exact mirror images of each other, so the design never drifts by one
pixel from one side to the other. The only unavoidable difference is half a pixel between odd and even
thickness, which is inherent to a pixel grid.

Stretched resolutions
---------------------
Playing at a stretched resolution (for example 1720x1080 on a 1920x1080 monitor) makes the game image
wider than it is rendered, so a crosshair drawn on the desktop looks narrower than the game's own
graphics. ``stretch`` is a ``(horizontal, vertical)`` pair of factors, normally from ``stretch_factors``.
Horizontal measurements are scaled by the first factor and vertical ones by the second, so every part of
the design is widened the same way the game image is, while staying exactly mirror symmetric.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from crosshair_data import DEFAULT_OUTLINE_COLOR

# The largest reach of any design from its center, in unstretched pixels:
# gap 40 + arm 80 + outline 6 = 126.
MAX_REACH = 126
OVERLAY_MARGIN = 10
# The default outline color; each crosshair can override it with its own ``outline_color``.
OUTLINE_COLOR = DEFAULT_OUTLINE_COLOR

MIN_STRETCH = 0.25
MAX_STRETCH = 3.0
MIN_GAME_SIZE = (640, 480)
MAX_GAME_SIZE = (7680, 4320)


def overlay_extent(stretch: tuple[float, float] = (1.0, 1.0)) -> tuple[int, int]:
    """Width and height of the overlay window that is guaranteed to hold the largest design."""
    sx, sy = stretch
    return (2 * (math.ceil(MAX_REACH * sx) + OVERLAY_MARGIN), 2 * (math.ceil(MAX_REACH * sy) + OVERLAY_MARGIN))


# Side length of the unstretched overlay window.
OVERLAY_SIZE = overlay_extent()[0]


def parse_resolution(text: str) -> tuple[int, int] | None:
    """Parse text such as ``1720x1080``. Returns None when the text means "no stretch"."""
    cleaned = text.strip().lower()
    if not cleaned or cleaned.startswith(("off", "native", "none")):
        return None
    match = re.fullmatch(r"(\d{3,4})\s*[x×*]\s*(\d{3,4})", cleaned)
    if not match:
        raise ValueError("Enter a resolution like 1720x1080, or choose Off.")
    width, height = int(match.group(1)), int(match.group(2))
    if not (MIN_GAME_SIZE[0] <= width <= MAX_GAME_SIZE[0] and MIN_GAME_SIZE[1] <= height <= MAX_GAME_SIZE[1]):
        raise ValueError("The resolution must be between 640x480 and 7680x4320.")
    return width, height


def stretch_factors(screen_size: tuple[int, int], game_size: tuple[int, int] | None) -> tuple[float, float]:
    """How much wider/taller the game's image is drawn than it is rendered.

    ``screen_size`` is the current desktop size and ``game_size`` the resolution the game renders at.
    If the game changes the desktop's own display mode, both are equal and the factor is 1 (the
    graphics card already stretches everything, including the overlay).
    """
    if game_size is None:
        return 1.0, 1.0
    factors = (screen_size[0] / game_size[0], screen_size[1] / game_size[1])
    return tuple(max(MIN_STRETCH, min(MAX_STRETCH, value)) for value in factors)  # type: ignore[return-value]


@dataclass(frozen=True)
class Rect:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass
class Geometry:
    outline: list[Rect]
    fill: list[Rect]
    center: tuple[float, float]

    def bounds(self) -> Rect | None:
        rects = self.outline + self.fill
        if not rects:
            return None
        return Rect(
            min(rect.x1 for rect in rects),
            min(rect.y1 for rect in rects),
            max(rect.x2 for rect in rects),
            max(rect.y2 for rect in rects),
        )


def _scaled(value: float, scale: float, minimum: int = 0) -> int:
    """Single rounding rule used for every dimension (round half up)."""
    return max(minimum, int(math.floor(value * scale + 0.5)))


def _ellipse_rows(cx: int, cy: int, dx: int, dy: int) -> dict[int, tuple[int, int]]:
    """Scanline spans (x1, x2) of a filled ellipse with outer diameters dx, dy.

    Pixel centers are tested against the ellipse equation. The span is mirrored around the center, so
    left and right edges always match, and rows are symmetric because the same formula is used above
    and below the center.
    """
    rows: dict[int, tuple[int, int]] = {}
    if dx <= 0 or dy <= 0:
        return rows
    center_x2 = 2 * cx + (dx % 2)  # twice the continuous center x
    center_y = cy + (dy % 2) * 0.5
    radius_x = dx / 2
    radius_y = dy / 2
    top = cy - dy // 2
    for y in range(top, top + dy):
        ny = (y + 0.5 - center_y) / radius_y
        inside = 1 - ny * ny
        if inside < 0:
            continue
        half = radius_x * math.sqrt(inside)
        x1 = math.ceil(center_x2 / 2 - half - 0.5 - 1e-9)
        x2 = center_x2 - x1
        if x2 > x1:
            rows[y] = (x1, x2)
    return rows


def _filled_ellipse(cx: int, cy: int, dx: int, dy: int) -> list[Rect]:
    return [Rect(x1, y, x2, y + 1) for y, (x1, x2) in sorted(_ellipse_rows(cx, cy, dx, dy).items())]


def _ring(cx: int, cy: int, outer_dx: int, outer_dy: int, inner_dx: int, inner_dy: int) -> list[Rect]:
    outer = _ellipse_rows(cx, cy, outer_dx, outer_dy)
    inner = _ellipse_rows(cx, cy, inner_dx, inner_dy)
    rects: list[Rect] = []
    for y, (ox1, ox2) in sorted(outer.items()):
        if y not in inner:
            rects.append(Rect(ox1, y, ox2, y + 1))
            continue
        ix1, ix2 = inner[y]
        if ix1 > ox1:
            rects.append(Rect(ox1, y, ix1, y + 1))
        if ox2 > ix2:
            rects.append(Rect(ix2, y, ox2, y + 1))
    return rects


def build_geometry(settings, center_x: int, center_y: int, scale: float = 1.0,
                   stretch: tuple[float, float] = (1.0, 1.0)) -> Geometry:
    """Return the outline and fill rectangles for ``settings`` centered on pixel (center_x, center_y).

    ``scale`` zooms everything uniformly (the editor's zoom buttons). ``stretch`` additionally widens
    or heightens the design to match a stretched game resolution.
    """
    cx, cy = int(center_x), int(center_y)
    sx = scale * stretch[0]
    sy = scale * stretch[1]
    # Horizontal measurements use sx, vertical measurements use sy.
    outline_x = _scaled(settings.outline, sx, 1) if settings.outline > 0 else 0
    outline_y = _scaled(settings.outline, sy, 1) if settings.outline > 0 else 0
    thick_x = _scaled(settings.thickness, sx, 1)  # width of vertical arms / ring width at left and right
    thick_y = _scaled(settings.thickness, sy, 1)  # height of horizontal arms / ring width at top and bottom

    if settings.shape == "Dot":
        diameter_x = _scaled(settings.size, sx, 1)
        diameter_y = _scaled(settings.size, sy, 1)
        fill = _filled_ellipse(cx, cy, diameter_x, diameter_y)
        outline = _filled_ellipse(cx, cy, diameter_x + 2 * outline_x, diameter_y + 2 * outline_y) if outline_x else []
        return Geometry(outline, fill, (cx + (diameter_x % 2) * 0.5, cy + (diameter_y % 2) * 0.5))

    if settings.shape == "Circle":
        dx = _scaled(settings.size, sx, 2)
        dy = _scaled(settings.vertical_size, sy, 2)
        fill = _ring(cx, cy, dx, dy, dx - 2 * thick_x, dy - 2 * thick_y)
        outline: list[Rect] = []
        if outline_x:
            outline = _ring(
                cx, cy,
                dx + 2 * outline_x, dy + 2 * outline_y,
                dx - 2 * thick_x - 2 * outline_x, dy - 2 * thick_y - 2 * outline_y,
            )
        return Geometry(outline, fill, (cx + (dx % 2) * 0.5, cy + (dy % 2) * 0.5))

    length_x = _scaled(settings.size, sx, 1)
    length_y = _scaled(settings.vertical_size, sy, 1)
    gap_x = _scaled(settings.gap, sx)
    gap_y = _scaled(settings.gap, sy)
    odd_x = thick_x % 2
    odd_y = thick_y % 2
    column = cx - thick_x // 2  # first pixel column of the vertical arms
    row = cy - thick_y // 2  # first pixel row of the horizontal arms
    left_in, right_in = cx - gap_x, cx + odd_x + gap_x
    top_in, bottom_in = cy - gap_y, cy + odd_y + gap_y
    is_t = settings.shape == "T"  # a T has no top arm, like the in-game T style

    arms: list[tuple[Rect, str]] = []  # (rect, which end faces the center: l, r, t, b, or "" for none)
    if gap_x == 0:
        # One continuous horizontal bar, so there is never a one-pixel hole at the center.
        arms.append((Rect(left_in - length_x, row, right_in + length_x, row + thick_y), ""))
    else:
        arms.append((Rect(left_in - length_x, row, left_in, row + thick_y), "r"))
        arms.append((Rect(right_in, row, right_in + length_x, row + thick_y), "l"))
    if gap_y == 0:
        top_end = row if is_t else top_in - length_y
        arms.append((Rect(column, top_end, column + thick_x, bottom_in + length_y), ""))
    else:
        if not is_t:
            arms.append((Rect(column, top_in - length_y, column + thick_x, top_in), "b"))
        arms.append((Rect(column, bottom_in, column + thick_x, bottom_in + length_y), "t"))

    outline: list[Rect] = []
    if outline_x:
        clear_x = right_in - left_in
        clear_y = bottom_in - top_in
        inner_x = min(outline_x, clear_x // 2)
        inner_y = min(outline_y, clear_y // 2)
        for rect, facing in arms:
            # The outline grows outward on every side, but only a limited amount toward the center so
            # that facing arms never paint a dark patch over the middle of the crosshair.
            outline.append(Rect(
                rect.x1 - (inner_x if facing == "l" else outline_x),
                rect.y1 - (inner_y if facing == "t" else outline_y),
                rect.x2 + (inner_x if facing == "r" else outline_x),
                rect.y2 + (inner_y if facing == "b" else outline_y),
            ))
    fill = [rect for rect, _facing in arms]

    center = (column + thick_x / 2, row + thick_y / 2)
    if settings.shape == "Cross" and settings.center_dot:
        dot_x = _scaled(settings.dot_size, sx, 1)
        dot_y = _scaled(settings.dot_size, sy, 1)
        if dot_x % 2 != thick_x % 2:
            dot_x += 1  # keep the dot concentric with the arms
        if dot_y % 2 != thick_y % 2:
            dot_y += 1
        if outline_x:
            outline.extend(_filled_ellipse(cx, cy, dot_x + 2 * outline_x, dot_y + 2 * outline_y))
        fill.extend(_filled_ellipse(cx, cy, dot_x, dot_y))
    return Geometry(outline, fill, center)


def fit_scale(settings, half_extent: int, stretch: tuple[float, float] = (1.0, 1.0)) -> float:
    """Scale (at most 1) that makes the crosshair fit within ``half_extent`` pixels of its center."""
    bounds = build_geometry(settings, 0, 0, 1.0, stretch).bounds()
    if bounds is None:
        return 1.0
    reach = max(abs(bounds.x1), abs(bounds.y1), bounds.x2, bounds.y2)
    return min(1.0, half_extent / reach) if reach else 1.0


def blend_color(foreground: str, background: str, opacity: int) -> str:
    """Opacity preview: blend the crosshair color over a solid background."""
    alpha = max(0, min(100, opacity)) / 100
    channels = [
        int(math.floor(int(foreground[index:index + 2], 16) * alpha + int(background[index:index + 2], 16) * (1 - alpha) + 0.5))
        for index in (1, 3, 5)
    ]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def _luminance(color: str) -> float:
    """Relative luminance of a #RRGGBB color, using the WCAG definition."""
    channels = []
    for index in (1, 3, 5):
        value = int(color[index:index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two colors: 1.0 when identical, 21.0 for black and white."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def layer_colors(settings, background: str | None = None) -> tuple[str, str]:
    """Return ``(outline, fill)`` colors, blended onto ``background`` when one is given."""
    fill = settings.color
    outline = getattr(settings, "outline_color", OUTLINE_COLOR)
    if background is not None:
        fill = blend_color(fill, background, settings.opacity)
        outline = blend_color(outline, background, settings.opacity)
    return outline, fill


def draw_on_canvas(canvas, settings, center_x: int, center_y: int, scale: float = 1.0,
                   background: str | None = None, tag: str = "crosshair",
                   stretch: tuple[float, float] = (1.0, 1.0)) -> None:
    """Paint the crosshair pixel-exactly onto a Tk canvas.

    The rectangles are written into a ``PhotoImage`` (``put`` fills a half-open pixel rectangle), then
    placed at an integer position. Unset image pixels stay transparent, which keeps the overlay's
    color-key transparency working. ``background`` blends the colors for the editor preview; the
    desktop overlay passes ``None`` and uses real window opacity instead.
    """
    import tkinter as tk

    canvas.delete(tag)
    
    # Handle image crosshair shape
    if settings.shape == "Image" and settings.image_path:
        _draw_image_crosshair(canvas, settings, center_x, center_y, scale, stretch, tag)
        return
    
    geometry = build_geometry(settings, center_x, center_y, scale, stretch)
    bounds = geometry.bounds()
    if bounds is None:
        return
    outline_color, color = layer_colors(settings, background)
    image = tk.PhotoImage(master=canvas, width=bounds.width, height=bounds.height)
    for layer, layer_color in ((geometry.outline, outline_color), (geometry.fill, color)):
        for rect in layer:
            image.put(layer_color, to=(rect.x1 - bounds.x1, rect.y1 - bounds.y1, rect.x2 - bounds.x1, rect.y2 - bounds.y1))
    canvas.create_image(bounds.x1, bounds.y1, image=image, anchor="nw", tags=tag)
    canvas._sightline_image = image  # Tk drops images that nothing references


def _draw_image_crosshair(canvas, settings, center_x: int, center_y: int, scale: float,
                         stretch: tuple[float, float], tag: str) -> None:
    """Draw a custom image crosshair with optional background removal."""
    try:
        from PIL import Image, ImageTk
    except ImportError as error:
        raise RuntimeError("Pillow is required to render custom image crosshairs.") from error

    with Image.open(settings.image_path) as source:
        img = source.convert("RGBA")

    if settings.remove_background:
        img = _remove_background(img, settings.bg_tolerance)

    new_width, new_height = _scaled_image_size(img.width, img.height, settings.image_scale, scale, stretch)
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    if settings.opacity < 100:
        alpha = img.getchannel("A").point(lambda value: round(value * settings.opacity / 100))
        img.putalpha(alpha)

    photo = ImageTk.PhotoImage(img, master=canvas)
    x, y = _centered_image_position(center_x, center_y, new_width, new_height)
    canvas.create_image(x, y, image=photo, anchor="nw", tags=tag)
    canvas._sightline_image = photo  # Tk drops images that nothing references


def _scaled_image_size(width: int, height: int, image_scale: int, scale: float,
                       stretch: tuple[float, float]) -> tuple[int, int]:
    factor = image_scale / 100 * scale
    return (
        max(1, int(math.floor(width * factor * stretch[0] + 0.5))),
        max(1, int(math.floor(height * factor * stretch[1] + 0.5))),
    )


def _centered_image_position(center_x: int, center_y: int, width: int, height: int) -> tuple[int, int]:
    return center_x - width // 2, center_y - height // 2


def _remove_background(img, tolerance: int):
    """Remove background color based on top-left corner pixel color."""
    pixels = img.load()
    ref_color = pixels[0, 0]
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if (abs(r - ref_color[0]) <= tolerance
                    and abs(g - ref_color[1]) <= tolerance
                    and abs(b - ref_color[2]) <= tolerance):
                pixels[x, y] = (r, g, b, 0)
    return img