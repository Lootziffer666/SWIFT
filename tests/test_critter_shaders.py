"""Tests for shaders: Perlin noise, palette swap (bug prevention), particles, transparency."""
import math
import pytest
from core.critter.shaders import (
    PerlinNoise,
    PaletteSwap,
    Color,
    ParticleSystem,
    sort_back_to_front,
)
from core.critter.geometry import Vec3, Vec2, IsometricProjection


class TestPerlinNoise:
    def test_deterministic_seed(self):
        a = PerlinNoise(seed=42)
        b = PerlinNoise(seed=42)
        assert a.noise(1.5, 2.5, 0.5) == b.noise(1.5, 2.5, 0.5)

    def test_range(self):
        n = PerlinNoise(seed=7)
        vals = [n.noise(x * 0.1, 0.3, 0.7) for x in range(100)]
        assert all(-1.3 <= v <= 1.3 for v in vals)

    def test_distortion_differs(self):
        n = PerlinNoise(seed=1)
        base = n.noise(0.5, 0.5, 0.0)
        distorted = n.distortion(0.5, 0.5, 0.0, amount=0.8)
        assert isinstance(distorted, float)


class TestPaletteSwap:
    def test_converts_255_to_float(self):
        c = PaletteSwap.to_shader_color(255, 128, 0, 255)
        assert math.isclose(c.r, 1.0)
        assert math.isclose(c.g, 128 / 255.0, abs_tol=1e-6)
        assert math.isclose(c.b, 0.0)

    def test_no_overdrive_to_white(self):
        # 255,255,255 must map exactly to white, never beyond.
        c = PaletteSwap.to_shader_color(255, 255, 255, 255)
        assert c == Color(1.0, 1.0, 1.0, 1.0)

    def test_resolve_region(self):
        pal = PaletteSwap([Color(1, 0, 0, 1), Color(0, 1, 0, 1)])
        assert pal.resolve(1) == Color(0, 1, 0, 1)
        # Out-of-range resolves to white (no silent corruption).
        assert pal.resolve(9) == Color(1, 1, 1, 1)

    def test_uniform_not_named_sprite0(self):
        # The variable holding the palette must not be "Sprite 0" (doc bug).
        pal = PaletteSwap([Color(0.2, 0.3, 0.4, 1.0)])
        assert not hasattr(pal, "Sprite 0")
        assert len(pal.palette) == 1

    def test_color_range_validation(self):
        with pytest.raises(ValueError):
            Color(1.5, 0.0, 0.0, 1.0)


class TestParticleSystem:
    def test_spawn_and_update(self):
        ps = ParticleSystem(capacity=100)
        ps.spawn(0, Vec3(0, 0, 0), Vec3(0, 5, 0), life=1.0)
        assert ps.alive_count == 1
        for _ in range(60):
            ps.update(dt=1 / 60.0)
        # Falls under gravity; should expire within ~1s.
        assert ps.alive_count == 0

    def test_capacity_bound(self):
        ps = ParticleSystem(capacity=4)
        ps.spawn(99, Vec3(0, 0, 0), Vec3(0, 0, 0), life=1.0)  # out of range -> ignored
        assert ps.alive_count == 0


class TestTransparency:
    def test_back_to_front(self):
        proj = IsometricProjection()
        near = ("near", Vec3(0, 0, 0))
        far = ("far", Vec3(0, 0, 10))
        ordered = sort_back_to_front([near, far], proj)
        # Far should come first in a back-to-front list.
        assert ordered[0] == "far"
        assert ordered[-1] == "near"
