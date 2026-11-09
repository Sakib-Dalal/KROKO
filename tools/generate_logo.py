#!/usr/bin/env python3
"""Generate the KROKO logo: a halftone crocodile, as an SVG.

Halftone is tonal reproduction by dot AREA, never by dot colour or opacity: a fixed
grid of cells whose diameter encodes lightness. That rule drives everything here. The
grid is one 45-degree mono screen, the paper is warm stock rather than white, and the
ink is near-black rather than #000.

The figure is drawn in an arbitrary source space and auto-fitted into the frame, so a
coordinate mistake in the drawing can never silently crop the animal.

Usage:
    python3 tools/generate_logo.py assets
"""
import math
import os
import sys

CELL = 10.0
ANGLE = 45.0
INK = "#171717"
PAPER = "#f2eee2"
WIDTH = 1024
HEIGHT = 320
PADDING = 40

BODY = (
    (30, 250), (80, 222), (140, 205), (200, 196), (260, 190), (320, 186),
    (380, 183), (440, 181), (500, 180), (560, 180), (620, 182), (670, 185),
    (700, 178), (730, 172), (780, 176), (860, 184), (940, 192), (985, 198),
    (996, 206), (940, 212), (880, 214), (820, 214), (770, 212), (740, 208),
    (738, 232), (780, 236), (850, 238), (920, 236), (975, 230), (982, 238),
    (920, 246), (850, 250), (780, 252), (740, 252), (700, 268), (660, 280),
    (600, 292), (540, 298), (480, 300), (420, 298), (360, 292), (300, 284),
    (240, 274), (180, 264), (120, 256), (70, 252),
)

LEGS = (
    ((330, 286), (368, 288), (372, 330), (398, 338), (330, 340), (322, 332)),
    ((404, 292), (442, 294), (446, 336), (472, 344), (404, 346), (396, 338)),
    ((598, 288), (636, 284), (642, 326), (668, 334), (600, 336), (592, 328)),
    ((672, 276), (710, 272), (716, 314), (742, 322), (674, 324), (666, 316)),
)

SCUTES = (
    (250, 190, 16), (318, 186, 17), (386, 183, 17), (454, 181, 17),
    (522, 180, 16), (590, 180, 16), (652, 183, 14), (700, 179, 11),
)

EYE = (764, 189, 12.0)


def scute(apex_x, apex_y, height):
    """One back scute as a small triangle."""
    half = height * 0.9
    return ((apex_x - half, apex_y), (apex_x, apex_y - height), (apex_x + half, apex_y))


def shapes():
    """Every polygon that carries ink, legs and scutes included."""
    found = [BODY]
    found.extend(LEGS)
    for apex_x, apex_y, height in SCUTES:
        found.append(scute(apex_x, apex_y, height))
    return found


def bounds(polys):
    """Bounding box of every polygon."""
    xs = [point[0] for poly in polys for point in poly]
    ys = [point[1] for poly in polys for point in poly]
    return min(xs), min(ys), max(xs), max(ys)


def fit(polys):
    """Scale and offset that centre the figure in the frame with padding."""
    left, top, right, bottom = bounds(polys)
    scale = min((WIDTH - 2 * PADDING) / (right - left), (HEIGHT - 2 * PADDING) / (bottom - top))
    offset_x = (WIDTH - (right - left) * scale) / 2 - left * scale
    offset_y = (HEIGHT - (bottom - top) * scale) / 2 - top * scale
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


def tone(x, y):
    """Lightness in source space: dark along the back, falling away at belly and ends."""
    body = 0.94 - 0.52 * min(1.0, max(0.0, (y - 180.0) / 120.0))
    tail = 1.0 - 0.40 * min(1.0, max(0.0, (140.0 - x) / 110.0))
    snout = 1.0 - 0.28 * min(1.0, max(0.0, (x - 900.0) / 96.0))
    return max(0.22, min(0.96, body * tail * snout))


def radius(coverage):
    """Dot radius from tonal coverage, capped so neighbouring dots never merge."""
    return min(math.sqrt(max(coverage, 0.0) * CELL * CELL / math.pi), CELL * 0.62)


def dots(polys):
    """Every dot centre in the frame, on a rotated grid, clipped to the silhouette."""
    scale, offset_x, offset_y = fit(polys)
    radians = math.radians(ANGLE)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    reach = int(math.hypot(WIDTH, HEIGHT) / CELL) + 2
    found = []
    for row in range(-reach, reach):
        for column in range(-reach, reach):
            u = column * CELL
            v = row * CELL
            paint_x = WIDTH / 2 + u * cos_a - v * sin_a
            paint_y = HEIGHT / 2 + u * sin_a + v * cos_a
            source_x = (paint_x - offset_x) / scale
            source_y = (paint_y - offset_y) / scale
            if not any(inside((source_x, source_y), shape) for shape in polys):
                continue
            found.append((paint_x, paint_y, radius(tone(source_x, source_y))))
    return found, scale, offset_x, offset_y


def render(found, scale, offset_x, offset_y):
    """Assemble the SVG document."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" ',
        f'width="{WIDTH}" height="{HEIGHT}" role="img" ',
        'aria-label="KROKO: a crocodile printed in a halftone dot screen">\n',
        f'  <rect width="{WIDTH}" height="{HEIGHT}" rx="26" fill="{PAPER}"/>\n',
        f'  <g fill="{INK}">\n',
    ]
    eye_x = EYE[0] * scale + offset_x
    eye_y = EYE[1] * scale + offset_y
    parts.append(f'    <circle cx="{eye_x:.1f}" cy="{eye_y:.1f}" r="{EYE[2] * scale:.1f}" fill="{PAPER}"/>\n')
    for x, y, r in found:
        parts.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}"/>\n')
    parts.append("  </g>\n</svg>\n")
    return "".join(parts)


def main(argv):
    """Write the logo and report the measurements."""
    target = argv[0] if argv else "assets"
    os.makedirs(target, exist_ok=True)
    polys = shapes()
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
