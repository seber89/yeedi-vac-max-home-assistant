"""Original static vector markers over an internally generated PNG, memory only."""
import base64
import math

from .map_data import RobotPosition, DockPosition
from .raw_map import assemble, display_geometry


def marker_position(position, major, geometry):
    """Legacy zero-degree, centered coordinates; invalid markers are omitted."""
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
    source_x = x / major.pixel + major.side / 2
    source_y = -y / major.pixel + major.side / 2
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
        self.geometry = display_geometry(assemble(raw.major, raw.pieces), raw.major.side)
        self._encoded = base64.b64encode(raw.png).decode("ascii")

    def render(self, robot, dock):
        g = self.geometry
        robot_xy = marker_position(robot, self.raw.major, g)
        dock_xy = marker_position(dock, self.raw.major, g)
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
