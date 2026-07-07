"""
Critter Crosser – Signed Distance Fields (SDF).

Organic creatures are built from SDFs instead of polygon meshes. The shader
evaluates, per pixel, a distance function; the surface is where the signed
distance is zero. Because the field is evaluated analytically (not by
transforming vertices), the "twisting"/pinching artefacts of polygon joints
under extreme rotation disappear, and organic "jelly" shapes come from
sinusoidal displacement + smooth blending of base shapes.

Performance: the GPU only evaluates the field inside each monster's
screen-space bounding box — never a full-screen pass.
"""
from dataclasses import dataclass
from typing import Callable

from core.critter.geometry import Vec2, Vec3, IsometricProjection


def sdf_sphere(p: Vec3, center: Vec3, radius: float) -> float:
    return p.distance_to(center) - radius


def sdf_capsule(p: Vec3, a: Vec3, b: Vec3, radius: float) -> float:
    pa = p - a
    ba = b - a
    h = min(max(pa.dot(ba) / ba.dot(ba), 0.0), 1.0)
    d = pa - ba * h
    return d.length - radius


def sdf_box(p: Vec3, center: Vec3, half: Vec3, round_: float = 0.0) -> float:
    q = p - center
    dx = abs(q.x) - half.x
    dy = abs(q.y) - half.y
    dz = abs(q.z) - half.z
    outside = Vec3(max(dx, 0.0), max(dy, 0.0), max(dz, 0.0)).length
    inside = min(max(dx, max(dy, dz)), 0.0)
    return outside + inside - round_


def sdf_union(a: float, b: float) -> float:
    return min(a, b)


def sdf_smooth_union(a: float, b: float, k: float) -> float:
    """Polynomial smin — produces the organic jelly blend between shapes."""
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * h * k * (1.0 / 6.0)


def sdf_sinusoidal_displace(
    base: float,
    p: Vec3,
    frequency: float,
    amplitude: float,
    phase: float,
    direction: Vec3,
) -> float:
    """Push/pull the field along `direction` with a sine wave (pulsation)."""
    import math
    wave = math.sin(p.dot(direction) * frequency + phase) * amplitude
    return base - wave


@dataclass
class BoundingBox:
    min: Vec2
    max: Vec2

    @property
    def width(self) -> float:
        return self.max.x - self.min.x

    @property
    def height(self) -> float:
        return self.max.y - self.min.y

    def contains(self, p: Vec2) -> bool:
        return self.min.x <= p.x <= self.max.x and self.min.y <= p.y <= self.max.y


class SDFRenderer:
    """
    CPU reference of the per-bounding-box SDF rasteriser. The production path
    is a fragment shader that runs the same `field` closure per pixel, but only
    inside each creature's bounding box.
    """

    def __init__(self, projection: IsometricProjection = None):
        self.projection = projection or IsometricProjection()

    def rasterize(
        self,
        box: BoundingBox,
        field: Callable[[Vec3], float],
        sample_step: float = 1.0,
    ) -> list:
        """
        Evaluate `field` for every screen pixel in `box`. Returns a 2D grid of
        signed distances (negative = inside the creature).
        """
        buffer: list = []
        y = box.min.y
        while y <= box.max.y:
            row: list = []
            x = box.min.x
            while x <= box.max.x:
                screen = Vec2(x, y)
                world = self.projection.unproject(screen)
                row.append(field(world))
                x += sample_step
            buffer.append(row)
            y += sample_step
        return buffer

    def occupancy_mask(self, box: BoundingBox, field, sample_step: float = 1.0) -> list:
        """Boolean inside/outside mask for the bounding box."""
        grid = self.rasterize(box, field, sample_step)
        return [[d <= 0.0 for d in row] for row in grid]
