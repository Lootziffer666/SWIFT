"""SDF (Signed Distance Field) rendering system for procedural character generation."""

from .primitives import Sphere, Box, Capsule, Torus, Plane, Vec3, SDFShape
from .operations import Union, Intersection, Subtraction, SmoothUnion, SmoothSubtraction
from .transform import Transform, Translate, Rotate, Scale
from .composition import SDFComposite, ColoredShape
from .renderer import SDFRenderer

__all__ = [
    'Sphere', 'Box', 'Capsule', 'Torus', 'Plane',
    'Vec3', 'SDFShape',
    'Union', 'Intersection', 'Subtraction', 'SmoothUnion', 'SmoothSubtraction',
    'Transform', 'Translate', 'Rotate', 'Scale',
    'SDFComposite', 'ColoredShape',
    'SDFRenderer'
]
