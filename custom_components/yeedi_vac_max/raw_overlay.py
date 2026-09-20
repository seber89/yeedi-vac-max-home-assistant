"""Original static vector markers over an internally generated PNG, memory only."""
import base64
import math

from .map_data import RobotPosition, DockPosition
from .raw_map import assemble, display_geometry


def source_position(position, major, rotation=0):
    """Clockwise quarter turns in the top-down raster coordinate system."""
    if not isinstance(position, (RobotPosition, DockPosition)):
        return None
    x, y = position.x, position.y
    if type(x) not in (int, float) or type(y) not in (int, float):
        return None
    try:
        if not math.isfinite(x) or not math.isfinite(y):
            return None
    except OverflowError:
        return None
    dx, dy = x / major.pixel, -y / major.pixel
    turns = {0: (dx, dy), 90: (-dy, dx), 180: (-dx, -dy), 270: (dy, -dx)}
    if rotation not in turns:
        return None
    dx, dy = turns[rotation]
    return dx + major.side / 2, dy + major.side / 2


def marker_position(position, major, geometry, rotation=0):
    source = source_position(position, major, rotation)
    if source is None:
        return None
    source_x, source_y = source
    if not (0 <= source_x < major.side and 0 <= source_y < major.side):
        return None
    # Only the actual cropped source area, not distant empty grid or padding.
    if not (geometry.left <= source_x < geometry.left + geometry.visible_width
            and geometry.top <= source_y < geometry.top + geometry.visible_height):
        return None
    return ((source_x - geometry.left + geometry.padding) * geometry.scale,
            (source_y - geometry.top + geometry.padding) * geometry.scale)


class RawOverlay:
    """Cache shared crop geometry and PNG encoding once per immutable RawMap."""

    def __init__(self, raw):
        self.raw = raw
        self._raster = assemble(raw.major, raw.pieces)
        self.geometry = display_geometry(self._raster, raw.major.side)
        self.candidates = {0, 90, 180, 270}
        self._encoded = base64.b64encode(raw.png).decode("ascii")

    def render(self, robot, dock):
        g = self.geometry
        if len(self.candidates) > 1:
            for position, tolerance in ((dock, 1), (robot, 0)):
                plausible = {angle for angle in (0, 90, 180, 270)
                             if self._plausible(position, angle, tolerance)}
                # No matching candidate is not evidence for any orientation.
                # Ignore missing, invalid or wholly inconsistent observations.
                if plausible:
                    self.candidates.intersection_update(plausible)
        if len(self.candidates) != 1:
            return self.raw.png, "image/png"
        angle = next(iter(self.candidates))
        robot_xy = self._marker(robot, angle, 0)
        dock_xy = self._marker(dock, angle, 1)
        if robot_xy is None and dock_xy is None:
            return self.raw.png, "image/png"
        radius = max(2, min(7, min(g.width, g.height) * .035))
        stroke = max(1, radius * .25)
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{g.width}" height="{g.height}" '
                 f'viewBox="0 0 {g.width} {g.height}">',
                 f'<image width="{g.width}" height="{g.height}" href="data:image/png;base64,{self._encoded}"/>']
        if dock_xy is not None:
            x, y = dock_xy
            parts.append(f'<rect id="dock" x="{x-radius:.3f}" y="{y-radius:.3f}" '
                         f'width="{2*radius:.3f}" height="{2*radius:.3f}" '
                         f'fill="#d97706" stroke="#fff" stroke-width="{stroke:.3f}"/>')
        if robot_xy is not None:
            x, y = robot_xy
            parts.append(f'<circle id="robot" cx="{x:.3f}" cy="{y:.3f}" r="{radius:.3f}" '
                         f'fill="#1677d2" stroke="#fff" stroke-width="{stroke:.3f}"/>')
        parts.append("</svg>")
        return "".join(parts).encode("utf-8"), "image/svg+xml"

    def _plausible(self, position, angle, tolerance):
        point = source_position(position, self.raw.major, angle)
        if point is None:
            return False
        x, y = point
        side = self.raw.major.side
        if not (0 <= x < side and 0 <= y < side):
            return False
        ix, iy = math.floor(x), math.floor(y)
        return any(self._raster[py * side + px]
                   for py in range(max(0, iy-tolerance), min(side, iy+tolerance+1))
                   for px in range(max(0, ix-tolerance), min(side, ix+tolerance+1)))

    def _marker(self, position, angle, tolerance):
        if not self._plausible(position, angle, tolerance):
            return None
        x, y = source_position(position, self.raw.major, angle)
        g = self.geometry
        # Dock tolerance may extend one source cell into the existing padding.
        px, py = (x-g.left+g.padding)*g.scale, (y-g.top+g.padding)*g.scale
        return (px, py) if 0 <= px < g.width and 0 <= py < g.height else None
