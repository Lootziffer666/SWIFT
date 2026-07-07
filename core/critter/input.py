"""
Critter Crosser – input evolution (twin-stick / mouse).

The original D-pad was replaced because real-time rotation felt laggy
("fighting the controls"). Twin-stick decouples look direction from movement
direction and allows side-stepping: movement comes from one vector, aim from
another, both applied immediately with no rotation interpolation.
"""
from dataclasses import dataclass
from typing import Tuple

from core.critter.geometry import Vec2


@dataclass
class TwinStickController:
    """
    movement : 2D vector from the left stick / WASD (already normalised-ish).
    aim      : 2D vector from the right stick / mouse (look direction).
    """

    movement: Vec2 = Vec2(0.0, 0.0)
    aim: Vec2 = Vec2(0.0, 1.0)

    def set_movement(self, x: float, y: float) -> None:
        self.movement = Vec2(x, y)

    def set_aim(self, x: float, y: float) -> None:
        if x == 0.0 and y == 0.0:
            return
        self.aim = Vec2(x, y).normalized()

    def velocity(self, speed: float) -> Vec2:
        """Immediate movement vector (no rotation lag)."""
        m = self.movement
        l = m.length
        if l <= 0.0:
            return Vec2(0.0, 0.0)
        return m * (speed / l if l > 1.0 else speed)

    def facing_angle(self) -> float:
        """Angle of the aim vector (radians)."""
        import math
        return math.atan2(self.aim.y, self.aim.x)

    def can_side_step(self) -> bool:
        """True when moving perpendicular to where the critter looks."""
        m = self.movement.normalized()
        a = self.aim.normalized()
        dot = abs(m.dot(a))
        return dot < 0.5  # roughly perpendicular
