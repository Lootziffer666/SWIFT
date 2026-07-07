"""SDF primitive shapes (Sphere, Box, Capsule, Torus)."""

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Vec3:
    """3D vector."""
    x: float
    y: float
    z: float

    def __add__(self, other):
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def length(self):
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z

    def normalize(self):
        l = self.length()
        if l < 1e-6:
            return Vec3(0, 0, 0)
        return Vec3(self.x / l, self.y / l, self.z / l)


class SDFShape:
    """Base class for SDF shapes."""

    def distance(self, p: Vec3) -> float:
        """Compute signed distance from point p to shape.
        Negative = inside, positive = outside.
        """
        raise NotImplementedError


class Sphere(SDFShape):
    """Sphere: |p| - r"""

    def __init__(self, center: Vec3, radius: float):
        self.center = center
        self.radius = radius

    def distance(self, p: Vec3) -> float:
        rel = p - self.center
        return rel.length() - self.radius

    def __repr__(self):
        return f"Sphere(center=({self.center.x},{self.center.y},{self.center.z}), r={self.radius})"


class Box(SDFShape):
    """Axis-aligned box (AABB).
    Distance from p to box with dimensions (dx, dy, dz) centered at origin.
    """

    def __init__(self, center: Vec3, dimensions: Tuple[float, float, float]):
        self.center = center
        self.dx, self.dy, self.dz = dimensions

    def distance(self, p: Vec3) -> float:
        rel = p - self.center
        q = Vec3(
            abs(rel.x) - self.dx / 2,
            abs(rel.y) - self.dy / 2,
            abs(rel.z) - self.dz / 2
        )
        # Outside corner distance
        outside = max(q.x, q.y, q.z)
        # Inside corner distance (negative)
        inside_dist = min(outside, 0)
        # Return combined distance
        q_clamped = Vec3(max(q.x, 0), max(q.y, 0), max(q.z, 0))
        return inside_dist + q_clamped.length()

    def __repr__(self):
        return f"Box(center=({self.center.x},{self.center.y},{self.center.z}), dims={self.dx},{self.dy},{self.dz})"


class Capsule(SDFShape):
    """Capsule (rounded cylinder): |p - closest_point_on_axis| - radius.
    Axis is vertical (Y).
    """

    def __init__(self, center: Vec3, radius: float, height: float):
        self.center = center
        self.radius = radius
        self.height = height

    def distance(self, p: Vec3) -> float:
        rel = p - self.center
        # Clamp y to capsule height
        half_h = self.height / 2
        y_clamped = max(-half_h, min(rel.y, half_h))

        # Point on axis closest to p
        closest = Vec3(0, y_clamped, 0)

        # Distance from p to axis
        to_axis = rel - closest
        return to_axis.length() - self.radius

    def __repr__(self):
        return f"Capsule(center=({self.center.x},{self.center.y},{self.center.z}), r={self.radius}, h={self.height})"


class Torus(SDFShape):
    """Torus (doughnut): ||(||(x,y,z)||.xy - R, z)|| - r
    Large radius R, small radius r, axis is Z.
    """

    def __init__(self, center: Vec3, major_radius: float, minor_radius: float):
        self.center = center
        self.major_radius = major_radius  # R (distance from center to tube center)
        self.minor_radius = minor_radius  # r (tube radius)

    def distance(self, p: Vec3) -> float:
        rel = p - self.center
        # Distance from z-axis in XY plane
        dist_xy = math.sqrt(rel.x**2 + rel.y**2)
        # Point on the major circle
        q = Vec3(dist_xy - self.major_radius, 0, rel.z)
        # Distance to tube
        return q.length() - self.minor_radius

    def __repr__(self):
        return f"Torus(center=({self.center.x},{self.center.y},{self.center.z}), R={self.major_radius}, r={self.minor_radius})"


class Plane(SDFShape):
    """Infinite plane defined by normal and distance from origin."""

    def __init__(self, normal: Vec3, d: float):
        self.normal = normal.normalize()
        self.d = d

    def distance(self, p: Vec3) -> float:
        return self.normal.dot(p) - self.d

    def __repr__(self):
        return f"Plane(n=({self.normal.x},{self.normal.y},{self.normal.z}), d={self.d})"
