"""Unit tests for SDF primitive shapes and operations."""

import math
import pytest
from core.sdf import (
    Vec3, Sphere, Box, Capsule, Torus, Plane,
    Union, Intersection, Subtraction, SmoothUnion, SmoothSubtraction,
    Transform, Translate, Rotate, Scale
)


class TestVec3:
    """Test Vec3 vector helper class."""

    def test_vec3_creation(self):
        v = Vec3(1, 2, 3)
        assert v.x == 1 and v.y == 2 and v.z == 3

    def test_vec3_addition(self):
        v1 = Vec3(1, 2, 3)
        v2 = Vec3(4, 5, 6)
        v3 = v1 + v2
        assert v3.x == 5 and v3.y == 7 and v3.z == 9

    def test_vec3_subtraction(self):
        v1 = Vec3(5, 7, 9)
        v2 = Vec3(1, 2, 3)
        v3 = v1 - v2
        assert v3.x == 4 and v3.y == 5 and v3.z == 6

    def test_vec3_multiplication(self):
        v = Vec3(1, 2, 3)
        v2 = v * 2
        assert v2.x == 2 and v2.y == 4 and v2.z == 6

    def test_vec3_length(self):
        v = Vec3(3, 4, 0)
        assert abs(v.length() - 5.0) < 1e-6

    def test_vec3_dot(self):
        v1 = Vec3(1, 2, 3)
        v2 = Vec3(4, 5, 6)
        dot = v1.dot(v2)
        assert dot == 32  # 1*4 + 2*5 + 3*6

    def test_vec3_normalize(self):
        v = Vec3(3, 4, 0)
        n = v.normalize()
        assert abs(n.length() - 1.0) < 1e-6

    def test_vec3_normalize_zero(self):
        v = Vec3(0, 0, 0)
        n = v.normalize()
        assert n.x == 0 and n.y == 0 and n.z == 0


class TestPrimitives:
    """Test SDF primitive shapes."""

    def test_sphere_at_center(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        # Point at center should be -radius
        assert abs(sphere.distance(Vec3(0, 0, 0)) - (-1.0)) < 1e-6

    def test_sphere_on_surface(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        # Point on surface should be ~0
        assert abs(sphere.distance(Vec3(1, 0, 0))) < 1e-6

    def test_sphere_outside(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        # Point outside should be positive
        assert sphere.distance(Vec3(3, 0, 0)) > 0

    def test_sphere_with_offset(self):
        sphere = Sphere(Vec3(5, 5, 5), 1.0)
        # Distance from (6, 5, 5) to center (5, 5, 5) is 1, minus radius 1 = 0
        assert abs(sphere.distance(Vec3(6, 5, 5))) < 1e-6

    def test_box_at_center(self):
        box = Box(Vec3(0, 0, 0), (2, 2, 2))
        # At center, distance should be -1 (half of dimensions)
        assert abs(box.distance(Vec3(0, 0, 0)) - (-1.0)) < 1e-6

    def test_box_on_surface(self):
        box = Box(Vec3(0, 0, 0), (2, 2, 2))
        # On face (x=1, y=0, z=0)
        assert abs(box.distance(Vec3(1, 0, 0))) < 1e-6

    def test_box_outside(self):
        box = Box(Vec3(0, 0, 0), (2, 2, 2))
        # Far outside
        assert box.distance(Vec3(5, 5, 5)) > 0

    def test_capsule_at_center(self):
        capsule = Capsule(Vec3(0, 0, 0), 0.5, 2.0)
        # At center, distance should be -radius
        assert abs(capsule.distance(Vec3(0, 0, 0)) - (-0.5)) < 1e-6

    def test_capsule_on_axis(self):
        capsule = Capsule(Vec3(0, 0, 0), 1.0, 2.0)
        # On cylinder axis at (0, 0.5, 0)
        assert abs(capsule.distance(Vec3(1, 0.5, 0))) < 1e-6

    def test_plane_above(self):
        plane = Plane(Vec3(0, 1, 0), 0)  # Normal up, distance 0 = at origin
        # Point above should be positive
        assert plane.distance(Vec3(0, 1, 0)) > 0

    def test_plane_below(self):
        plane = Plane(Vec3(0, 1, 0), 0)
        # Point below should be negative
        assert plane.distance(Vec3(0, -1, 0)) < 0


class TestOperations:
    """Test SDF composition operations."""

    def test_union_min(self):
        s1 = Sphere(Vec3(0, 0, 0), 1.0)
        s2 = Sphere(Vec3(3, 0, 0), 1.0)
        union = Union(s1, s2)
        # At (0,0,0): s1 gives -1, s2 gives ~1.7 → min = -1
        d1 = union.distance(Vec3(0, 0, 0))
        assert abs(d1 - (-1.0)) < 1e-6

    def test_intersection_max(self):
        s1 = Sphere(Vec3(0, 0, 0), 2.0)
        s2 = Sphere(Vec3(0, 0, 0), 1.0)
        intersection = Intersection(s1, s2)
        # At center: s1 gives -2, s2 gives -1 → max = -1
        d = intersection.distance(Vec3(0, 0, 0))
        assert abs(d - (-1.0)) < 1e-6

    def test_subtraction(self):
        outer = Sphere(Vec3(0, 0, 0), 2.0)
        inner = Sphere(Vec3(0, 0, 0), 1.0)
        shell = Subtraction(outer, inner)
        # At (1.5, 0, 0): outer=-0.5 (inside), inner=0.5 (outside)
        # max(-0.5, -0.5) = -0.5 (in the shell)
        d = shell.distance(Vec3(1.5, 0, 0))
        assert d < 0  # Inside the shell

        # At (2.5, 0, 0): outer=0.5 (outside), inner=1.5 (outside)
        # max(0.5, -1.5) = 0.5 (outside the shell)
        d2 = shell.distance(Vec3(2.5, 0, 0))
        assert d2 > 0  # Outside the shell

    def test_smooth_union(self):
        s1 = Sphere(Vec3(-1, 0, 0), 1.0)
        s2 = Sphere(Vec3(1, 0, 0), 1.0)
        smooth = SmoothUnion(s1, s2, k=0.5)
        # Smooth union should be differentiable at blend region
        d = smooth.distance(Vec3(0, 0, 0))
        # Between -1 and -1, should be less harsh
        assert -1.0 < d < 0

    def test_smooth_subtraction(self):
        outer = Sphere(Vec3(0, 0, 0), 2.0)
        inner = Sphere(Vec3(0, 0, 0), 1.0)
        shell = SmoothSubtraction(outer, inner, k=0.2)
        d = shell.distance(Vec3(0, 0, 0))
        # Should be inside outer but outside inner with smooth transition
        assert isinstance(d, float)


class TestTransforms:
    """Test SDF transform operations."""

    def test_translate(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        translated = Translate(sphere, Vec3(5, 0, 0))
        # Translated sphere should have center at (5,0,0)
        # At (6,0,0): relative to center is (1,0,0), distance = 0
        d = translated.distance(Vec3(6, 0, 0))
        assert abs(d) < 1e-6

    def test_scale(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        scaled = Scale(sphere, Vec3(2, 2, 2))
        # Scaled by 2, so radius becomes 2
        # At (2,0,0): relative distance should be ~0
        d = scaled.distance(Vec3(2, 0, 0))
        assert abs(d) < 1e-6

    def test_rotate_z(self):
        box = Box(Vec3(0, 0, 0), (2, 2, 2))
        # Rotate 90 degrees around Z
        rotated = Rotate(box, Vec3(0, 0, math.pi / 2))
        # Should still have similar distance properties
        d_center = rotated.distance(Vec3(0, 0, 0))
        d_original = box.distance(Vec3(0, 0, 0))
        assert abs(d_center - d_original) < 1e-5

    def test_transform_combined(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        # Translate, then scale
        transformed = Transform(
            sphere,
            translate=Vec3(5, 0, 0),
            scale=Vec3(2, 2, 2)
        )
        # Center should now be at (5, 0, 0) with radius 2
        d = transformed.distance(Vec3(7, 0, 0))
        assert abs(d) < 1e-6

    def test_translate_shorthand(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        t = Translate(sphere, Vec3(3, 4, 0))
        # At (4, 4, 0) relative distance is 1
        d = t.distance(Vec3(4, 4, 0))
        assert abs(d) < 1e-6


class TestCompositeCharacter:
    """Test building a simple character from primitives."""

    def test_simple_humanoid(self):
        """Create a simple humanoid: head + body."""
        head = Sphere(Vec3(0, 2, 0), 0.5)
        body = Capsule(Vec3(0, 0, 0), 0.4, 1.5)
        character = Union(head, body)

        # At head center, should be negative (inside)
        assert character.distance(Vec3(0, 2, 0)) < 0

        # At body center, should be negative
        assert character.distance(Vec3(0, 0, 0)) < 0

        # Far outside, should be positive
        assert character.distance(Vec3(10, 10, 10)) > 0

    def test_humanoid_with_transforms(self):
        """Create head offset from body using transforms."""
        head = Sphere(Vec3(0, 0, 0), 0.5)
        head_positioned = Translate(head, Vec3(0, 2, 0))

        body = Capsule(Vec3(0, 0, 0), 0.4, 1.5)

        character = Union(head_positioned, body)

        # Head at (0, 2, 0) should be inside
        assert character.distance(Vec3(0, 2, 0)) < 0

        # Body at (0, 0, 0) should be inside
        assert character.distance(Vec3(0, 0, 0)) < 0
