"""Tests for the fake-3D projection and SDF pipeline."""
import math
from core.critter.geometry import Vec3, IsometricProjection, Vec2
from core.critter.sdf import (
    sdf_sphere,
    sdf_capsule,
    sdf_smooth_union,
    sdf_sinusoidal_displace,
    BoundingBox,
    SDFRenderer,
)


class TestIsometricProjection:
    def test_project_origin(self):
        proj = IsometricProjection()
        assert proj.project(Vec3(0, 0, 0)) == Vec2(0.0, 0.0)

    def test_project_symmetric(self):
        proj = IsometricProjection(scale=32)
        a = proj.project(Vec3(1, 0, 0))
        b = proj.project(Vec3(0, 0, -1))
        assert a.x == b.x and a.y == b.y

    def test_roundtrip(self):
        proj = IsometricProjection(scale=32, origin=Vec2(10, 20))
        p = Vec3(3, 1.5, -2)
        s = proj.project(p)
        back = proj.unproject(s, height=p.y)
        assert math.isclose(back.x, p.x, abs_tol=1e-4)
        assert math.isclose(back.z, p.z, abs_tol=1e-4)


class TestSDF:
    def test_sphere_inside_outside(self):
        c = Vec3(0, 0, 0)
        assert sdf_sphere(Vec3(0, 0, 0), c, 1.0) < 0
        assert sdf_sphere(Vec3(2, 0, 0), c, 1.0) > 0
        assert math.isclose(sdf_sphere(Vec3(1, 0, 0), c, 1.0), 0.0, abs_tol=1e-6)

    def test_capsule(self):
        d = sdf_capsule(Vec3(0, 0, 0), Vec3(-1, 0, 0), Vec3(1, 0, 0), 0.5)
        assert d < 0  # on the segment -> inside
        assert sdf_capsule(Vec3(0, 5, 0), Vec3(-1, 0, 0), Vec3(1, 0, 0), 0.5) > 0

    def test_smooth_union_blends(self):
        # Overlapping spheres within the blend radius k -> the union bulges
        # outward, i.e. its signed distance is *more* negative than min(a,b).
        a = sdf_sphere(Vec3(0, 0, 0), Vec3(0, 0, 0), 1.0)
        b = sdf_sphere(Vec3(0.3, 0, 0), Vec3(0.3, 0, 0), 1.0)
        hard = min(a, b)
        soft = sdf_smooth_union(a, b, k=0.5)
        assert soft < hard  # smooth union is "fatter" between the shapes

    def test_sinusoidal_displace_changes_field(self):
        base = sdf_sphere(Vec3(0.5, 0, 0), Vec3(0, 0, 0), 1.0)
        disp = sdf_sinusoidal_displace(
            base, Vec3(0.5, 0, 0), frequency=2.0, amplitude=0.2, phase=0.0,
            direction=Vec3(0, 1, 0),
        )
        assert disp != base

    def test_renderer_bounded_only(self):
        proj = IsometricProjection(scale=8)
        renderer = SDFRenderer(proj)
        box = BoundingBox(Vec2(-80, -80), Vec2(80, 80))
        field = lambda p: sdf_sphere(p, Vec3(0, 0, 0), 2.0)
        grid = renderer.rasterize(box, field, sample_step=4.0)
        # Only a small region of the big box is inside the radius-2 sphere.
        inside = sum(1 for row in grid for d in row if d <= 0)
        total = sum(len(row) for row in grid)
        assert 0 < inside < total
