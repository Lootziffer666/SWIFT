"""SDF transform operations (Translate, Rotate, Scale)."""

from .primitives import SDFShape, Vec3
import math


class Transform(SDFShape):
    """Apply translation, rotation, and scale to an SDF shape.
    Transforms are applied in reverse order: scale → rotate → translate.
    """

    def __init__(
        self,
        shape: SDFShape,
        translate: Vec3 = None,
        rotate: Vec3 = None,
        scale: Vec3 = None,
    ):
        self.shape = shape
        self.translate = translate or Vec3(0, 0, 0)
        self.rotate = rotate or Vec3(0, 0, 0)
        self.scale = scale or Vec3(1, 1, 1)

    def distance(self, p: Vec3) -> float:
        # Inverse transform: p → p' (local space)
        # 1. Undo translation
        p = p - self.translate

        # 2. Undo rotation (apply inverse rotation matrices)
        p = self._rotate_inverse(p)

        # 3. Undo scale (divide by scale factor)
        if self.scale.x != 0 and self.scale.y != 0 and self.scale.z != 0:
            p = Vec3(p.x / self.scale.x, p.y / self.scale.y, p.z / self.scale.z)

        # Evaluate shape in local space
        d = self.shape.distance(p)

        # Scale the distance (SDF property: distance scales with geometry)
        # Use minimum scale factor to be conservative
        scale_factor = min(abs(self.scale.x), abs(self.scale.y), abs(self.scale.z))
        if scale_factor > 0:
            d = d * scale_factor

        return d

    def _rotate_inverse(self, p: Vec3) -> Vec3:
        """Apply inverse rotation by rotating -rx, -ry, -rz in reverse order."""
        # Rotation angles (in radians)
        rx, ry, rz = self.rotate.x, self.rotate.y, self.rotate.z

        # Undo Z rotation: rotate around Z by -rz
        cos_z, sin_z = math.cos(-rz), math.sin(-rz)
        p = Vec3(
            p.x * cos_z - p.y * sin_z,
            p.x * sin_z + p.y * cos_z,
            p.z,
        )

        # Undo Y rotation: rotate around Y by -ry
        cos_y, sin_y = math.cos(-ry), math.sin(-ry)
        p = Vec3(
            p.x * cos_y + p.z * sin_y,
            p.y,
            -p.x * sin_y + p.z * cos_y,
        )

        # Undo X rotation: rotate around X by -rx
        cos_x, sin_x = math.cos(-rx), math.sin(-rx)
        p = Vec3(
            p.x,
            p.y * cos_x - p.z * sin_x,
            p.y * sin_x + p.z * cos_x,
        )

        return p

    def __repr__(self):
        return f"Transform({self.shape}, translate={self.translate}, rotate={self.rotate}, scale={self.scale})"


class Translate(Transform):
    """Shorthand for translating a shape."""

    def __init__(self, shape: SDFShape, offset: Vec3):
        super().__init__(shape, translate=offset)

    def __repr__(self):
        return f"Translate({self.shape}, {self.translate})"


class Rotate(Transform):
    """Shorthand for rotating a shape (angles in radians)."""

    def __init__(self, shape: SDFShape, angles: Vec3):
        super().__init__(shape, rotate=angles)

    def __repr__(self):
        return f"Rotate({self.shape}, {self.rotate})"


class Scale(Transform):
    """Shorthand for scaling a shape uniformly or per-axis."""

    def __init__(self, shape: SDFShape, factors: Vec3):
        super().__init__(shape, scale=factors)

    def __repr__(self):
        return f"Scale({self.shape}, {self.scale})"
