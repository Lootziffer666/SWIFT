"""SDF composition: combine shapes with materials and colors."""

from dataclasses import dataclass
from typing import List, Tuple
from .primitives import SDFShape, Vec3


@dataclass
class ColoredShape:
    """An SDF shape with a color and material properties."""

    shape: SDFShape
    color: Tuple[int, int, int]  # RGB 0-255
    material: str = "default"  # e.g., "skin", "metal", "cloth"
    roughness: float = 0.5
    metallic: float = 0.0


class SDFComposite:
    """Composite SDF: union of multiple colored shapes.
    Evaluates all shapes, returns the closest (minimum distance).
    """

    def __init__(self, shapes: List[ColoredShape]):
        self.shapes = shapes

    def distance(self, p: Vec3) -> float:
        """Return minimum signed distance to any shape."""
        if not self.shapes:
            return 1e9
        return min(shape.shape.distance(p) for shape in self.shapes)

    def distance_with_material(self, p: Vec3) -> Tuple[float, int]:
        """Return (distance, shape_index) of closest shape (by absolute distance to surface)."""
        if not self.shapes:
            return 1e9, -1

        min_abs_dist = 1e9
        closest_idx = -1
        closest_dist = 1e9
        for i, cs in enumerate(self.shapes):
            d = cs.shape.distance(p)
            abs_d = abs(d)
            if abs_d < min_abs_dist:
                min_abs_dist = abs_d
                closest_idx = i
                closest_dist = d
        return closest_dist, closest_idx

    def get_color(self, p: Vec3) -> Tuple[int, int, int]:
        """Get the RGB color at point p (closest shape's color)."""
        _, idx = self.distance_with_material(p)
        if idx >= 0:
            return self.shapes[idx].color
        return (128, 128, 128)  # Gray default

    def get_material(self, p: Vec3) -> str:
        """Get the material type at point p."""
        _, idx = self.distance_with_material(p)
        if idx >= 0:
            return self.shapes[idx].material
        return "default"
