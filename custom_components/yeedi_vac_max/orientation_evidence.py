"""Bounded private orientation observations, RAM only and never a route history."""
import math

from .map_data import RobotPosition, identifier

LIMIT = 16


class OrientationEvidence:
    def __init__(self):
        self._map_id = None
        self._points = ()

    def bind(self, map_id):
        if type(map_id) is not str or identifier(map_id) != map_id or map_id == '0':
            return
        if self._map_id != map_id:
            self._map_id = map_id
            self._points = ()

    def record(self, map_id, position):
        if not isinstance(position, RobotPosition):
            return
        x, y = position.x, position.y
        if type(x) not in (int, float) or type(y) not in (int, float):
            return
        try:
            if not math.isfinite(x) or not math.isfinite(y):
                return
        except OverflowError:
            return
        self.bind(map_id)
        if self._map_id != map_id or self._map_id is None:
            return
        point = RobotPosition(x, y)  # Angle is neither evidence nor interpreted.
        if point not in self._points:
            self._points = (*self._points, point)[-LIMIT:]

    def points_for(self, map_id):
        return self._points if self._map_id == map_id else ()

    def clear(self):
        self._map_id = None
        self._points = ()
