"""
Critter Crosser – visual effects & shader techniques.

~90% of the visual complexity comes from Perlin-noise manipulation and GPU
math. This module provides the CPU reference implementations that mirror the
shader logic: Perlin noise (scrolling / distortion / stretch), runtime palette
swapping (with the documented bug-prevention rules), a GPU-friendly particle
system, and the fixed-camera back-to-front transparency sort.
"""
import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple

from core.critter.geometry import Vec2, Vec3, IsometricProjection


class PerlinNoise:
    """Classic improved Perlin noise (3D), seeded deterministic permutation."""

    def __init__(self, seed: int = 0):
        p = list(range(256))
        state = (seed + 0x9E3779B9) & 0xFFFFFFFF
        for i in range(255, 0, -1):
            state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFF
            j = state % (i + 1)
            p[i], p[j] = p[j], p[i]
        self.perm = p + p

    @staticmethod
    def _fade(t: float) -> float:
        return t * t * t * (t * (t * 6 - 15) + 10)

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    @staticmethod
    def _grad(h: int, x: float, y: float, z: float) -> float:
        h &= 15
        u = x if h < 8 else y
        v = y if h < 4 else (z if h in (12, 14) else x)
        return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)

    def noise(self, x: float, y: float, z: float) -> float:
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        Z = int(math.floor(z)) & 255
        xf, yf, zf = x - math.floor(x), y - math.floor(y), z - math.floor(z)
        u, v, w = self._fade(xf), self._fade(yf), self._fade(zf)
        A = self.perm[X] + Y
        AA, AB = self.perm[A] + Z, self.perm[A + 1] + Z
        B = self.perm[X + 1] + Y
        BA, BB = self.perm[B] + Z, self.perm[B + 1] + Z

        x1 = self._lerp(self._grad(self.perm[AA], xf, yf, zf),
                        self._grad(self.perm[BA], xf - 1, yf, zf), u)
        x2 = self._lerp(self._grad(self.perm[AB], xf, yf - 1, zf),
                        self._grad(self.perm[BB], xf - 1, yf - 1, zf), u)
        y1 = self._lerp(x1, x2, v)
        x3 = self._lerp(self._grad(self.perm[AA + 1], xf, yf, zf - 1),
                        self._grad(self.perm[BA + 1], xf - 1, yf, zf - 1), u)
        x4 = self._lerp(self._grad(self.perm[AB + 1], xf, yf - 1, zf - 1),
                        self._grad(self.perm[BB + 1], xf - 1, yf - 1, zf - 1), u)
        y2 = self._lerp(x3, x4, v)
        return self._lerp(y1, y2, w)

    # ── Documented usage patterns ─────────────────────────────────────────
    def scrolling(self, x: float, y: float, time: float) -> float:
        """Flowing water / fog / clouds: animate the time axis."""
        return self.noise(x, y, time)

    def distortion(self, x: float, y: float, time: float, amount: float) -> float:
        """Electricity / magic / heat-haze: offset one field by another."""
        ox = self.noise(x + 31.4, y, time) * amount
        oy = self.noise(x, y + 17.2, time) * amount
        return self.noise(x + ox, y + oy, time)

    def stretched(self, x: float, y: float, time: float, scale: float) -> float:
        """Waves / organic pulsation: scale the sample coordinate."""
        return self.noise(x * scale, y * scale, time)


@dataclass
class Color:
    r: float
    g: float
    b: float
    a: float = 1.0

    def __post_init__(self):
        for name in ("r", "g", "b", "a"):
            v = getattr(self, name)
            if v < 0.0 or v > 1.0:
                raise ValueError(f"{name} out of shader range 0..1: {v}")
        self.r = min(max(self.r, 0.0), 1.0)
        self.g = min(max(self.g, 0.0), 1.0)
        self.b = min(max(self.b, 0.0), 1.0)
        self.a = min(max(self.a, 0.0), 1.0)

    @staticmethod
    def white() -> "Color":
        return Color(1.0, 1.0, 1.0, 1.0)


class PaletteSwap:
    """
    Runtime palette swapping via ID-color masks.

    CRITICAL BUG PREVENTION:
      * The uniform array MUST NOT be named "Sprite 0". That name collided
        with a debug sprite and caused random color corruption + stretching
        artefacts. We name it `palette`.
      * RGB values (0..255) MUST be converted to shader floats (0.0..1.0),
        otherwise the pipeline over-drives to pure white.
    """

    def __init__(self, palette: List[Color] = None):
        self.palette: List[Color] = list(palette) if palette else []

    def resolve(self, region_id: int) -> Color:
        if 0 <= region_id < len(self.palette):
            return self.palette[region_id]
        return Color.white()

    @staticmethod
    def to_shader_color(r: int, g: int, b: int, a: int = 255) -> Color:
        return Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0)


class ParticleSystem:
    """
    GPU particle system. The mesh is allocated once at startup (struct of
    arrays) and mutated on the GPU, allowing ~1,000,000 particles at 60 FPS.
    This is the CPU mirror used for tests / headless preview.
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.positions: List[Vec3] = [Vec3(0, 0, 0) for _ in range(capacity)]
        self.velocities: List[Vec3] = [Vec3(0, 0, 0) for _ in range(capacity)]
        self.lifetimes: List[float] = [0.0] * capacity
        self.max_lifetimes: List[float] = [1.0] * capacity

    def spawn(self, index: int, position: Vec3, velocity: Vec3, life: float) -> None:
        if not (0 <= index < self.capacity):
            return
        self.positions[index] = position
        self.velocities[index] = velocity
        self.lifetimes[index] = life
        self.max_lifetimes[index] = life

    def update(self, dt: float, gravity: Vec3 = None) -> None:
        g = gravity or Vec3(0.0, -9.8, 0.0)
        for i in range(self.capacity):
            if self.lifetimes[i] <= 0:
                continue
            self.velocities[i] = self.velocities[i] + g * dt
            self.positions[i] = self.positions[i] + self.velocities[i] * dt
            self.lifetimes[i] -= dt

    @property
    def alive_count(self) -> int:
        return sum(1 for l in self.lifetimes if l > 0)


def sort_back_to_front(
    items: List[Tuple[object, Vec3]],
    projection: IsometricProjection = None,
) -> List[object]:
    """
    Single-pass transparency for the fixed camera: order renderables strictly
    back-to-front (far -> near) so no multi-pass blending is needed. Depth is
    the projected screen-Y (higher = further back in 2:1 iso) plus world depth.
    """
    proj = projection or IsometricProjection()
    scored = []
    for item, world in items:
        s = proj.project(world)
        # Larger screen-y == higher on screen == further back.
        scored.append((s.y, world.z, item))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [item for _, _, item in scored]
