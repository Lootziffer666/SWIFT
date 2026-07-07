"""Character definition: skeleton + SDF shapes for procedural character generation."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import json
from core.procedural.skeleton import SkeletonDef, create_humanoid_skeleton, scale_skeleton
from core.sdf import Vec3, Sphere, Box, Capsule, Torus, SDFShape, Transform, Translate, Scale


@dataclass
class ShapeAttachment:
    """SDF shape attached to a bone."""

    bone_name: str
    shape_type: str  # "sphere", "box", "capsule", "torus"
    params: Dict  # shape-specific parameters

    # Visual properties
    color: Tuple[int, int, int] = (200, 150, 100)  # RGB
    material: str = "skin"

    # Transform in bone space
    translate: Tuple[float, float, float] = (0, 0, 0)
    rotate: Tuple[float, float, float] = (0, 0, 0)
    scale: Tuple[float, float, float] = (1, 1, 1)


class CharacterDef:
    """Complete character definition: skeleton + SDF shapes."""

    def __init__(self, name: str, skeleton: SkeletonDef):
        self.name = name
        self.skeleton = skeleton
        self.shape_attachments: List[ShapeAttachment] = []
        self.palettes: Dict[str, Dict[str, str]] = {}  # name -> {color_key: hex_value}

    def add_shape(self, attachment: ShapeAttachment):
        """Add an SDF shape attachment."""
        self.shape_attachments.append(attachment)

    def add_palette(self, name: str, colors: Dict[str, str]):
        """Add a color palette."""
        self.palettes[name] = colors

    def build_sdf_shapes(self, bone_positions: Dict[str, Vec3]) -> List:
        """
        Build SDF shapes in world space given bone positions.

        Args:
            bone_positions: dict of bone_name -> Vec3 (world position)

        Returns:
            List of ColoredShape objects
        """
        from core.sdf.composition import ColoredShape

        colored_shapes = []

        for attachment in self.shape_attachments:
            # Get bone position
            bone_pos = bone_positions.get(attachment.bone_name, Vec3(0, 0, 0))

            # Create base shape
            shape = self._create_shape(attachment)

            # Apply bone-space transform
            if attachment.translate != (0, 0, 0) or attachment.scale != (1, 1, 1):
                translate = Vec3(*attachment.translate)
                scale = Vec3(*attachment.scale)
                shape = Transform(shape, translate=translate, scale=scale)

            # Translate to bone position
            shape = Translate(shape, bone_pos)

            # Create colored shape
            colored = ColoredShape(
                shape=shape,
                color=attachment.color,
                material=attachment.material,
            )
            colored_shapes.append(colored)

        return colored_shapes

    def _create_shape(self, attachment: ShapeAttachment) -> SDFShape:
        """Create an SDF shape from attachment definition."""
        shape_type = attachment.shape_type.lower()
        params = attachment.params

        if shape_type == "sphere":
            radius = params.get("radius", 0.1)
            return Sphere(Vec3(0, 0, 0), radius)

        elif shape_type == "box":
            dims = params.get("dimensions", (0.1, 0.1, 0.1))
            return Box(Vec3(0, 0, 0), tuple(dims))

        elif shape_type == "capsule":
            radius = params.get("radius", 0.05)
            height = params.get("height", 0.2)
            return Capsule(Vec3(0, 0, 0), radius, height)

        elif shape_type == "torus":
            major_radius = params.get("major_radius", 0.1)
            minor_radius = params.get("minor_radius", 0.03)
            return Torus(Vec3(0, 0, 0), major_radius, minor_radius)

        else:
            raise ValueError(f"Unknown shape type: {shape_type}")

    def to_dict(self) -> dict:
        """Export to dictionary (JSON-serializable)."""
        return {
            "name": self.name,
            "skeleton": {
                "root": self.skeleton.root_joint,
                "joints": [
                    {
                        "name": name,
                        "parent": joint.parent,
                        "offset": list(joint.offset),
                        "bone_length": joint.bone_length,
                    }
                    for name, joint in self.skeleton.joints.items()
                ],
            },
            "shapes": [
                {
                    "bone": a.bone_name,
                    "type": a.shape_type,
                    "params": a.params,
                    "color": a.color,
                    "material": a.material,
                    "transform": {
                        "translate": a.translate,
                        "rotate": a.rotate,
                        "scale": a.scale,
                    },
                }
                for a in self.shape_attachments
            ],
            "palettes": self.palettes,
        }

    @staticmethod
    def from_dict(data: dict) -> "CharacterDef":
        """Load from dictionary."""
        # Reconstruct skeleton
        skeleton = SkeletonDef(root_joint=data["skeleton"]["root"])
        for joint_data in data["skeleton"]["joints"]:
            skeleton.add_joint(
                name=joint_data["name"],
                parent=joint_data["parent"],
                offset=tuple(joint_data["offset"]),
                bone_length=joint_data["bone_length"],
            )

        # Create character
        char = CharacterDef(data["name"], skeleton)

        # Add shapes
        for shape_data in data.get("shapes", []):
            transform = shape_data.get("transform", {})
            attachment = ShapeAttachment(
                bone_name=shape_data["bone"],
                shape_type=shape_data["type"],
                params=shape_data["params"],
                color=tuple(shape_data.get("color", (200, 150, 100))),
                material=shape_data.get("material", "skin"),
                translate=tuple(transform.get("translate", (0, 0, 0))),
                rotate=tuple(transform.get("rotate", (0, 0, 0))),
                scale=tuple(transform.get("scale", (1, 1, 1))),
            )
            char.add_shape(attachment)

        # Add palettes
        for palette_name, colors in data.get("palettes", {}).items():
            char.add_palette(palette_name, colors)

        return char


def create_humanoid_character() -> CharacterDef:
    """Create a default humanoid character."""
    skeleton = create_humanoid_skeleton()
    char = CharacterDef("Humanoid Standard", skeleton)

    # Body (torso)
    char.add_shape(
        ShapeAttachment(
            bone_name="Spine",
            shape_type="capsule",
            params={"radius": 0.12, "height": 0.3},
            color=(200, 150, 100),  # Skin
            material="skin",
        )
    )

    # Head
    char.add_shape(
        ShapeAttachment(
            bone_name="Chest",
            shape_type="sphere",
            params={"radius": 0.1},
            color=(200, 150, 100),  # Skin
            material="skin",
            translate=(0, 0.2, 0),
        )
    )

    # Left arm
    char.add_shape(
        ShapeAttachment(
            bone_name="Arm.L",
            shape_type="capsule",
            params={"radius": 0.05, "height": 0.25},
            color=(200, 150, 100),  # Skin
            material="skin",
        )
    )

    # Right arm
    char.add_shape(
        ShapeAttachment(
            bone_name="Arm.R",
            shape_type="capsule",
            params={"radius": 0.05, "height": 0.25},
            color=(200, 150, 100),  # Skin
            material="skin",
        )
    )

    # Left leg
    char.add_shape(
        ShapeAttachment(
            bone_name="Leg.L",
            shape_type="capsule",
            params={"radius": 0.06, "height": 0.35},
            color=(200, 150, 100),  # Skin
            material="skin",
        )
    )

    # Right leg
    char.add_shape(
        ShapeAttachment(
            bone_name="Leg.R",
            shape_type="capsule",
            params={"radius": 0.06, "height": 0.35},
            color=(200, 150, 100),  # Skin
            material="skin",
        )
    )

    return char
