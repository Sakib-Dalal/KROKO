#!/usr/bin/env python3
"""Generate the KROKO logo: an evil front-facing crocodile in a halftone screen.

Halftone is tonal reproduction by dot AREA, never by dot colour or opacity: a fixed
grid of cells whose diameter encodes lightness. Here that inverts against a flat
profile version — the ground is dark and the ink is bone, so a large dot means light
and a small dot lets the dark ground through as shadow.

A front view is read from three cues, in this order: two eyes set inside raised brows,
a lit ridge running down the snout, and a dark mouth between two rows of teeth. Two
small holes placed near the centre of a pale face read as eye sockets, not nostrils, so
the snout is carried by the ridge alone.

The head is authored as one half and mirrored, so the face is symmetrical by
construction rather than by careful typing. The figure is auto-fitted into the frame,
so a coordinate mistake cannot silently crop the animal.

Palette: three inks, no more. Deep green ground, bone form, one blood accent for the
eyes. Never pure white, never pure black.

Usage:
    python3 tools/generate_logo.py assets
"""
import math
import os
import sys

GROUND = "#0a2418"
BONE = "#e8e1ce"
BLOOD = "#c8202e"
SIZE = 1024
CELL = 10.5
ANGLE = 45.0
PADDING = 26
TOOTH_PITCH = 32.5
TOP = -336.0
BOTTOM = 268.0
BROW_Y = -248.0

SKULL = (
    (0, -300), (44, -293), (84, -301), (104, -319), (124, -327), (148, -319),
    (168, -302), (186, -270), (196, -232), (203, -186), (204, -142), (196, -94),
    (190, -38), (208, 10),
)

LOWER_START = (0, 140)
LOWER_END = ((206, 166), (196, 214), (150, 246), (70, 262), (0, 268))
EYE_HALF = ((80, -296), (140, -308), (142, -286), (82, -274))
PUPIL = (110, -292, 6.5)


def tooth_row(first_x, base_y, drop, count):
    """Zigzag tooth edge inward from first_x, teeth pointing by the sign of drop."""
    points = []
    for index in range(count):
        left = first_x - index * TOOTH_PITCH
        points.append((left, base_y))
        points.append((left - TOOTH_PITCH * 0.5, base_y + drop))
    points.append((first_x - count * TOOTH_PITCH, base_y))
    return points


def mirror(points):
    """Reflect a half across the centre line, reversing the winding."""
    return [(-x, y) for x, y in reversed(points)]


def upper_jaw():
    """Skull, brow and the downward tooth row, as one half."""
    return SKULL + tuple(tooth_row(192, 10, 46, 5)) + ((0, 10),)


def lower_jaw():
    """The open lower jaw and its upward tooth row, as one half."""
    edge = tuple(reversed(tooth_row(180, 140, -56, 5)))
    return (LOWER_START,) + edge + LOWER_END


def head_polygons():
    """Both jaws, right half and mirrored left half."""
    upper = upper_jaw()
    lower = lower_jaw()
    return [upper, lower, mirror(upper), mirror(lower)]


def eye_polygons():
    """The two angled eye slits, mirrored."""
    return [EYE_HALF, mirror(EYE_HALF)]


def bounds(polys):
    """Bounding box of every polygon."""
    xs = [point[0] for poly in polys for point in poly]
    ys = [point[1] for poly in polys for point in poly]
    return min(xs), min(ys), max(xs), max(ys)


def fit(polys):
    """Scale and offset that centre the figure in the square frame with padding."""
    left, top, right, bottom = bounds(polys)
    scale = min((SIZE - 2 * PADDING) / (right - left), (SIZE - 2 * PADDING) / (bottom - top))
    offset_x = (SIZE - (right - left) * scale) / 2 - left * scale
    offset_y = (SIZE - (bottom - top) * scale) / 2 - top * scale
    return scale, offset_x, offset_y


def inside(point, points):
    """Ray-casting point-in-polygon test."""
    x, y = point
    hit = False
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if crossing > x:
                hit = not hit
    return hit


def half_width(y):
    """Approximate half-width of the head at height y, used to shape the ridge."""
    progress = min(1.0, max(0.0, (y - TOP) / (BOTTOM - TOP)))
    return 112.0 + 100.0 * progress


def brow_shade(x, y):
    """A soft dark band beneath the brow, which is what makes an eye look angry."""
    band = math.exp(-((y - BROW_Y) ** 2) / 1400.0)
    reach = min(1.0, abs(x) / 120.0)
    return 1.0 - 0.34 * band * reach


def tone(x, y):
    """Bone coverage: a lit ridge down the centre, falling to shadow at both flanks."""
    distance = min(1.0, abs(x) / half_width(y))
    ridge = 1.10 - 0.82 * distance ** 1.2
    jaw = 1.0 - 0.30 * min(1.0, max(0.0, (y - 30.0) / 200.0))
    return max(0.26, min(0.96, ridge * jaw * brow_shade(x, y)))


def radius(coverage):
    """Dot radius from tonal coverage, capped so neighbouring dots never merge."""
    return min(math.sqrt(max(coverage, 0.0) * CELL * CELL / math.pi), CELL * 0.62)


def dots(polys):
    """Every dot centre in the frame, on a rotated grid, clipped to the silhouette."""
    scale, offset_x, offset_y = fit(polys)
    radians = math.radians(ANGLE)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    reach = int(SIZE / CELL) + 2
    found = []
    for row in range(-reach, reach):
        for column in range(-reach, reach):
            paint_x = SIZE / 2 + (column * CELL) * cos_a - (row * CELL) * sin_a
            paint_y = SIZE / 2 + (column * CELL) * sin_a + (row * CELL) * cos_a
            source_x = (paint_x - offset_x) / scale
            source_y = (paint_y - offset_y) / scale
            if not any(inside((source_x, source_y), shape) for shape in polys):
                continue
            found.append((paint_x, paint_y, radius(tone(source_x, source_y))))
    return found, scale, offset_x, offset_y


def place(point, scale, offset_x, offset_y):
    """Map one source point into frame coordinates."""
    return point[0] * scale + offset_x, point[1] * scale + offset_y


def outline(poly, scale, offset_x, offset_y):
    """An SVG polygon point list in frame coordinates."""
    pairs = []
    for point in poly:
        x, y = place(point, scale, offset_x, offset_y)
        pairs.append(f"{x:.1f},{y:.1f}")
    return " ".join(pairs)


def circle(spec, scale, offset_x, offset_y):
    """An SVG circle element from a (x, y, r) source-space spec."""
    x, y = place(spec[:2], scale, offset_x, offset_y)
    return f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{spec[2] * scale:.1f}"/>\n'


def both(spec, scale, offset_x, offset_y):
    """One circle drawn on both sides of the centre line."""
    left = circle(spec, scale, offset_x, offset_y)
    return left + circle((-spec[0], spec[1], spec[2]), scale, offset_x, offset_y)


def render(found, scale, offset_x, offset_y):
    """Assemble the SVG document."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" ',
        f'width="{SIZE}" height="{SIZE}" role="img" ',
        'aria-label="KROKO: an evil front-facing crocodile printed in a halftone dot screen">\n',
        f'  <rect width="{SIZE}" height="{SIZE}" rx="150" fill="{GROUND}"/>\n',
        f'  <g fill="{BONE}">\n',
    ]
    for x, y, r in found:
        parts.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}"/>\n')
    parts.append("  </g>\n")
    parts.append(f'  <g fill="{BLOOD}">\n')
    for poly in eye_polygons():
        parts.append(f'    <polygon points="{outline(poly, scale, offset_x, offset_y)}"/>\n')
    parts.append("  </g>\n")
    parts.append(f'  <g fill="{GROUND}">\n')
    parts.append(both(PUPIL, scale, offset_x, offset_y))
    parts.append("  </g>\n</svg>\n")
    return "".join(parts)


def main(argv):
    """Write the logo and report the measurements."""
    target = argv[0] if argv else "assets"
    os.makedirs(target, exist_ok=True)
    polys = head_polygons()
    left, top, right, bottom = bounds(polys)
    found, scale, offset_x, offset_y = dots(polys)
    path = os.path.join(target, "kroko-logo.svg")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render(found, scale, offset_x, offset_y))
    print(f"figure bounds: {right - left:.0f} x {bottom - top:.0f} source units")
    print(f"fit scale: {scale:.3f}, offset: {offset_x:.1f}, {offset_y:.1f}")
    print(f"{path}: {len(found)} dots, {os.path.getsize(path)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
