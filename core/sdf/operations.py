"""SDF composition operations (Union, Intersection, Subtraction, Smooth blends)."""

from .primitives import SDFShape, Vec3
import math


class Union(SDFShape):
    """Union of two SDFs: min(d1, d2)"""

    def __init__(self, shape_a: SDFShape, shape_b: SDFShape):
        self.shape_a = shape_a
        self.shape_b = shape_b

    def distance(self, p: Vec3) -> float:
        return min(self.shape_a.distance(p), self.shape_b.distance(p))

    def __repr__(self):
        return f"Union({self.shape_a}, {self.shape_b})"


class Intersection(SDFShape):
    """Intersection of two SDFs: max(d1, d2)"""

    def __init__(self, shape_a: SDFShape, shape_b: SDFShape):
        self.shape_a = shape_a
        self.shape_b = shape_b

    def distance(self, p: Vec3) -> float:
        return max(self.shape_a.distance(p), self.shape_b.distance(p))

    def __repr__(self):
        return f"Intersection({self.shape_a}, {self.shape_b})"


class Subtraction(SDFShape):
    """Subtraction (A - B): max(d1, -d2)"""

    def __init__(self, shape_a: SDFShape, shape_b: SDFShape):
        self.shape_a = shape_a
        self.shape_b = shape_b

    def distance(self, p: Vec3) -> float:
        da = self.shape_a.distance(p)
        db = self.shape_b.distance(p)
        return max(da, -db)

    def __repr__(self):
        return f"Subtraction({self.shape_a}, {self.shape_b})"


class SmoothUnion(SDFShape):
    """Smooth union using polynomial blend: smoothstep(d1, d2, k)
    k controls blend radius (0.1-1.0 typical).
    """

    def __init__(self, shape_a: SDFShape, shape_b: SDFShape, k: float = 0.1):
        self.shape_a = shape_a
        self.shape_b = shape_b
        self.k = k

    def distance(self, p: Vec3) -> float:
        da = self.shape_a.distance(p)
        db = self.shape_b.distance(p)
        h = max(self.k - abs(da - db), 0) / self.k
        return min(da, db) - h * h * h * self.k / 6.0

    def __repr__(self):
        return f"SmoothUnion({self.shape_a}, {self.shape_b}, k={self.k})"


class SmoothSubtraction(SDFShape):
    """Smooth subtraction (A - B) using polynomial blend.
    k controls blend radius (0.1-1.0 typical).
    """

    def __init__(self, shape_a: SDFShape, shape_b: SDFShape, k: float = 0.1):
        self.shape_a = shape_a
        self.shape_b = shape_b
        self.k = k

    def distance(self, p: Vec3) -> float:
        da = self.shape_a.distance(p)
        db = self.shape_b.distance(p)
        h = max(self.k - abs(da + db), 0) / self.k
        return max(da, -db) + h * h * h * self.k / 6.0

    def __repr__(self):
        return f"SmoothSubtraction({self.shape_a}, {self.shape_b}, k={self.k})"
