"""SDF raymarching renderer: evaluate SDF and render to PNG."""

import math
from typing import Tuple, Optional
import numpy as np
from PIL import Image

from .primitives import Vec3
from .composition import SDFComposite


class SDFRenderer:
    """Render an SDF composite using CPU-side raymarching."""

    def __init__(
        self,
        composite: SDFComposite,
        resolution: Tuple[int, int] = (512, 512),
        camera_dist: float = 3.0,
        camera_fov: float = 45.0,
    ):
        """
        Args:
            composite: SDFComposite to render
            resolution: (width, height) in pixels
            camera_dist: distance from camera to origin (Z-axis)
            camera_fov: vertical field of view in degrees
        """
        self.composite = composite
        self.width, self.height = resolution
        self.camera_dist = camera_dist
        self.camera_fov = camera_fov

    def render(
        self,
        max_steps: int = 256,
        max_distance: float = 100.0,
        surface_threshold: float = 0.001,
        transparent: bool = False,
    ) -> Image.Image:
        """
        Render the SDF using raymarching.

        Args:
            max_steps: maximum raymarching iterations per pixel
            max_distance: maximum ray distance
            surface_threshold: distance threshold for surface detection
            transparent: when True, misses get alpha 0 (RGBA sprite output)
                         instead of the opaque gray background

        Returns:
            PIL Image (RGB, or RGBA when transparent=True)
        """
        # Initialize output buffer
        channels = 4 if transparent else 3
        pixels = np.zeros((self.height, self.width, channels), dtype=np.uint8)

        # Camera setup
        fov_rad = math.radians(self.camera_fov)
        height_at_dist = 2.0 * self.camera_dist * math.tan(fov_rad / 2.0)
        width_at_dist = height_at_dist * (self.width / self.height)

        # For each pixel
        for y in range(self.height):
            for x in range(self.width):
                # Normalized device coordinates
                ndc_x = (x + 0.5) / self.width
                ndc_y = (y + 0.5) / self.height

                # World space
                world_x = (ndc_x - 0.5) * width_at_dist
                world_y = (0.5 - ndc_y) * height_at_dist  # Flip Y

                # Ray from camera through pixel
                ray_origin = Vec3(0, 0, self.camera_dist)
                ray_target = Vec3(world_x, world_y, 0)
                ray_dir = (ray_target - ray_origin).normalize()

                # Raymarch
                hit, color = self._raymarch(
                    ray_origin,
                    ray_dir,
                    max_steps,
                    max_distance,
                    surface_threshold,
                )

                if transparent:
                    pixels[y, x] = (*color, 255) if hit else (0, 0, 0, 0)
                else:
                    pixels[y, x] = color

        # Convert to PIL Image
        img = Image.fromarray(pixels, mode="RGBA" if transparent else "RGB")
        return img

    def _raymarch(
        self,
        ray_origin: Vec3,
        ray_dir: Vec3,
        max_steps: int,
        max_distance: float,
        surface_threshold: float,
    ) -> Tuple[bool, Tuple[int, int, int]]:
        """
        Raymarch a single ray.

        Returns:
            (hit, color): whether a surface was hit, and RGB color
        """
        t = 0.0  # Distance along ray
        color = (64, 64, 64)  # Default: dark gray background

        for step in range(max_steps):
            # Current position along ray
            p = ray_origin + ray_dir * t

            # Evaluate SDF
            d = self.composite.distance(p)

            # Hit check
            if d <= surface_threshold:
                color = self.composite.get_color(p)

                # Simple lighting: estimate normal via gradient
                normal = self._estimate_normal(p, surface_threshold * 2)

                # Directional light
                light_dir = Vec3(1, 1, 1).normalize()
                diffuse = max(0.0, normal.dot(light_dir))

                # Tint color by diffuse + ambient
                ambient = 0.3
                brightness = ambient + diffuse * 0.7
                r = int(color[0] * brightness)
                g = int(color[1] * brightness)
                b = int(color[2] * brightness)
                color = (min(255, r), min(255, g), min(255, b))

                return True, color

            # Step forward
            t += max(d * 0.9, 0.01)  # Reduce step size a bit for safety

            # Max distance reached
            if t > max_distance:
                break

        # No hit: return background color
        return False, (32, 32, 32)

    def _estimate_normal(self, p: Vec3, epsilon: float) -> Vec3:
        """Estimate surface normal via central differences."""
        dx = Vec3(epsilon, 0, 0)
        dy = Vec3(0, epsilon, 0)
        dz = Vec3(0, 0, epsilon)

        d_dx = self.composite.distance(p + dx) - self.composite.distance(p - dx)
        d_dy = self.composite.distance(p + dy) - self.composite.distance(p - dy)
        d_dz = self.composite.distance(p + dz) - self.composite.distance(p - dz)

        normal = Vec3(d_dx, d_dy, d_dz)
        normalized = normal.normalize()
        # If normalize fails (zero vector), return default
        if normalized.length() < 1e-6:
            return Vec3(0, 0, 1)
        return normalized
