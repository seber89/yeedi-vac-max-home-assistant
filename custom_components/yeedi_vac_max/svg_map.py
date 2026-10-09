"""Original, static SVG rendering of validated in-memory room geometry."""
from html import escape
import math

COLORS = ("#b8d8ed", "#d9c2ed", "#bee3c5", "#f5dbad", "#efbec5", "#bde5df")


def render_map(rooms, robot=None, dock=None):
    """Return SVG bytes, or None without usable geometry. No network or files."""
    rooms = [r for r in rooms if r.polygon and len(r.polygon) >= 3
             and all(math.isfinite(v) for p in r.polygon for v in p)]
    if not rooms:
        return None
    points = [p for r in rooms for p in r.polygon]
    robot = robot if robot and all(math.isfinite(v) for v in (robot.x, robot.y)) else None
    dock = dock if dock and all(math.isfinite(v) for v in (dock.x, dock.y)) else None
    points += [(p.x, p.y) for p in (robot, dock) if p is not None]
    xs, ys = zip(*points)
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    pad, radius = span * .08, span * .018
    box = (min(xs)-pad, min(ys)-pad, max(xs)-min(xs)+2*pad, max(ys)-min(ys)+2*pad)
    if not all(math.isfinite(v) for v in box):
        return None
    def n(value):
        return format(value, ".12g")
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + ' '.join(map(n, box)) + '" role="img" aria-label="Map">']
    for index, room in enumerate(rooms):
        coords = ' '.join(f'{n(x)},{n(y)}' for x, y in room.polygon)
        out.append(f'<polygon points="{coords}" fill="{COLORS[index % len(COLORS)]}" stroke="#425466" stroke-width="{n(span*.003)}"/>')
        x = sum(p[0] / len(room.polygon) for p in room.polygon)
        y = sum(p[1] / len(room.polygon) for p in room.polygon)
        # XML 1.0 forbids most control characters, even in escaped text.
        name = ''.join(c for c in room.name if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
        out.append(f'<text x="{n(x)}" y="{n(y)}" text-anchor="middle" font-size="{n(span*.03)}" fill="#172b4d">{escape(name)}</text>')
    if dock:
        out.append(f'<rect class="dock" x="{n(dock.x-radius)}" y="{n(dock.y-radius)}" width="{n(2*radius)}" height="{n(2*radius)}" fill="#176b40" stroke="#ffffff" stroke-width="{n(radius*.2)}"/>')
    if robot:
        out.append(f'<circle class="robot" cx="{n(robot.x)}" cy="{n(robot.y)}" r="{n(radius)}" fill="#1769ce" stroke="#ffffff" stroke-width="{n(radius*.2)}"/>')
    out.append('</svg>')
    return ''.join(out).encode('utf-8')
