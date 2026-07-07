"""
Critter Crosser – geometry & fake-3D projection.

Implements the lightweight vector math and the isometric ("fake 3D")
projection used throughout the engine. Standard 3D perspective matrices
fail under the fixed iso/pseudo-3D camera, so we adapt Snyder's planar
map-projection idea: an orthographic 2:1 isometric transform that maps a
world point straight into screen space without a perspective divide.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, s: float) -> "Vec2":
        return Vec2(self.x * s, self.y * s)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec2):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    @property
    def length(self) -> float:
        return (self.x * self.x + self.y * self.y) ** 0.5

    def normalized(self) -> "Vec2":
        l = self.length
        return Vec2(self.x / l, self.y / l) if l > 0 else Vec2(0.0, 0.0)

    def distance_to(self, other: "Vec2") -> float:
        return (self - other).length

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec3):
            return NotImplemented
        return self.x == other.x and self.y == other.y and self.z == other.z

    @property
    def length(self) -> float:
        return (self.x * self.x + self.y * self.y + self.z * self.z) ** 0.5

    def normalized(self) -> "Vec3":
        l = self.length
        return Vec3(self.x / l, self.y / l, self.z / l) if l > 0 else Vec3(0.0, 0.0, 0.0)

    def distance_to(self, other: "Vec3") -> float:
        return (self - other).length

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )


@dataclass
class IsometricProjection:
    """
    Snyder-style planar projection for the fixed pseudo-3D camera.

    World space: x = right, y = up, z = depth.
    Screen space: 2:1 isometric diamond, height squashed vertically.
    """

    scale: float = 32.0
    vertical_squash: float = 0.5
    origin: Vec2 = Vec2(0.0, 0.0)

    def project(self, world: Vec3) -> Vec2:
        sx = (world.x - world.z) * self.scale
        sy = (world.x + world.z) * self.scale * self.vertical_squash - world.y * self.scale
        return Vec2(sx, sy) + self.origin

    def unproject(self, screen: Vec2, height: float = 0.0) -> Vec3:
        p = screen - self.origin
        a = p.x / self.scale
        b = (p.y + height * self.scale) / (self.scale * self.vertical_squash)
        x = (a + b) * 0.5
        z = (b - a) * 0.5
        return Vec3(x, height, z)
