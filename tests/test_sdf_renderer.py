"""Unit tests for SDF renderer."""

import pytest
from core.sdf import Sphere, Vec3
from core.sdf.composition import SDFComposite, ColoredShape
from core.sdf.renderer import SDFRenderer


class TestSDFComposition:
    """Test SDF composite operations."""

    def test_composite_single_shape(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (255, 0, 0), material="metal")
        composite = SDFComposite([colored])

        # At center, should be inside
        assert composite.distance(Vec3(0, 0, 0)) < 0

        # At (1, 0, 0), should be on surface
        assert abs(composite.distance(Vec3(1, 0, 0))) < 1e-6

    def test_composite_multiple_shapes(self):
        sphere1 = Sphere(Vec3(-0.8, 0, 0), 1.0)
        sphere2 = Sphere(Vec3(0.8, 0, 0), 1.0)

        colored1 = ColoredShape(sphere1, (255, 0, 0), material="metal")
        colored2 = ColoredShape(sphere2, (0, 0, 255), material="plastic")

        composite = SDFComposite([colored1, colored2])

        # Union behavior: minimum distance wins
        d_center = composite.distance(Vec3(0, 0, 0))
        d_far = composite.distance(Vec3(10, 0, 0))

        assert d_center < 0  # Inside both spheres (they overlap at center)
        assert d_far > 0  # Outside all spheres

    def test_composite_get_color(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (100, 150, 200), material="skin")
        composite = SDFComposite([colored])

        color = composite.get_color(Vec3(0, 0, 0))
        assert color == (100, 150, 200)

    def test_composite_get_material(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (255, 0, 0), material="cloth")
        composite = SDFComposite([colored])

        material = composite.get_material(Vec3(0, 0, 0))
        assert material == "cloth"

    def test_composite_closest_shape_wins(self):
        """Test that composite returns color of nearest shape (by surface distance)."""
        sphere1 = Sphere(Vec3(0, 0, 0), 2.0)
        sphere2 = Sphere(Vec3(0, 0, 0), 1.0)

        colored1 = ColoredShape(sphere1, (255, 0, 0), material="red")
        colored2 = ColoredShape(sphere2, (0, 0, 255), material="blue")

        composite = SDFComposite([colored1, colored2])

        # At center, sphere2 surface is nearest (distance 1)
        # sphere1 distance is -2, sphere2 distance is -1
        # absolute distances: 2 vs 1, so sphere2 wins
        _, idx = composite.distance_with_material(Vec3(0, 0, 0))
        assert idx == 1
        assert composite.get_color(Vec3(0, 0, 0)) == (0, 0, 255)


class TestSDFRenderer:
    """Test SDF raymarching renderer."""

    def test_renderer_initialization(self):
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (255, 0, 0))
        composite = SDFComposite([colored])

        renderer = SDFRenderer(
            composite,
            resolution=(256, 256),
            camera_dist=3.0,
        )

        assert renderer.width == 256
        assert renderer.height == 256
        assert renderer.camera_dist == 3.0

    def test_renderer_renders_image(self):
        """Test that renderer produces an image."""
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (200, 100, 50))
        composite = SDFComposite([colored])

        renderer = SDFRenderer(
            composite,
            resolution=(64, 64),  # Small for speed
            camera_dist=3.0,
        )

        img = renderer.render(max_steps=64)

        # Check image properties
        assert img.size == (64, 64)
        assert img.mode == "RGB"

        # Image should not be all black or all white
        pixels = list(img.getdata())
        pixel_values = set(pixels)
        assert len(pixel_values) > 1  # At least some variation

    def test_renderer_sphere_in_center(self):
        """Test that a centered sphere renders at center of image."""
        sphere = Sphere(Vec3(0, 0, 0), 0.8)
        colored = ColoredShape(sphere, (255, 128, 64))
        composite = SDFComposite([colored])

        renderer = SDFRenderer(
            composite,
            resolution=(128, 128),
            camera_dist=3.0,
        )

        img = renderer.render(max_steps=128)

        # Center pixel should be the colored sphere (not background)
        center_pixel = img.getpixel((64, 64))
        # Center should have the sphere's color or lit version of it
        assert center_pixel != (32, 32, 32)  # Not pure background

    def test_renderer_output_consistency(self):
        """Test that rendering is deterministic."""
        sphere = Sphere(Vec3(0, 0, 0), 1.0)
        colored = ColoredShape(sphere, (255, 0, 0))
        composite = SDFComposite([colored])

        renderer = SDFRenderer(composite, resolution=(32, 32))

        img1 = renderer.render(max_steps=32)
        img2 = renderer.render(max_steps=32)

        # Same input should produce same output
        assert list(img1.getdata()) == list(img2.getdata())
