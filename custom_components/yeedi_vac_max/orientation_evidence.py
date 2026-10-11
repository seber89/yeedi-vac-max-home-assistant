"""Bounded private orientation observations, RAM only and never a route history."""
import math

from .map_data import RobotPosition, identifier

LIMIT = 16


class OrientationEvidence:
    def __init__(self):
        self._map_id = None
        self._points = ()
        self._rotation = None

    def bind(self, map_id):
        if type(map_id) is not str or identifier(map_id) != map_id or map_id == '0':
            return
        if self._map_id != map_id:
            self._map_id = map_id
            self._points = ()
            self._rotation = None

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

    def rotation_for(self, map_id):
        return self._rotation if self._map_id == map_id else None

    def confirm_rotation(self, map_id, rotation):
        if type(rotation) is not int or rotation not in (0, 90, 180, 270):
            return
        self.bind(map_id)
        if self._map_id == map_id and self._map_id is not None:
            self._rotation = rotation

    def forget_rotation(self, map_id):
        if self._map_id == map_id:
            self._rotation = None

    def clear(self):
        self._map_id = None
        self._points = ()
        self._rotation = None
