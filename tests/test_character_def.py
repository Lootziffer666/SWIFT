"""Unit tests for character definition system."""

import json
import pytest
from core.procedural.skeleton import create_humanoid_skeleton
from core.procedural.character_def import (
    ShapeAttachment,
    CharacterDef,
    create_humanoid_character,
)
from core.sdf import Vec3


class TestCharacterDef:
    """Test character definition and skeleton integration."""

    def test_character_creation(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        assert char.name == "TestChar"
        assert len(char.shape_attachments) == 0

    def test_add_shape(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        attachment = ShapeAttachment(
            bone_name="Spine",
            shape_type="sphere",
            params={"radius": 0.1},
            color=(255, 0, 0),
        )

        char.add_shape(attachment)
        assert len(char.shape_attachments) == 1
        assert char.shape_attachments[0].bone_name == "Spine"

    def test_add_palette(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        colors = {"skin": "#C9A876", "hair": "#3D2817"}
        char.add_palette("default", colors)

        assert "default" in char.palettes
        assert char.palettes["default"]["skin"] == "#C9A876"

    def test_build_sdf_shapes(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        char.add_shape(
            ShapeAttachment(
                bone_name="Spine",
                shape_type="sphere",
                params={"radius": 0.1},
            )
        )

        # Provide bone positions
        bone_positions = {
            "Hips": Vec3(0, 0, 0),
            "Spine": Vec3(0, 0.3, 0),
            "Chest": Vec3(0, 0.7, 0),
        }

        shapes = char.build_sdf_shapes(bone_positions)
        assert len(shapes) == 1
        assert shapes[0].color == (200, 150, 100)  # Default color

    def test_to_dict(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        char.add_shape(
            ShapeAttachment(
                bone_name="Spine",
                shape_type="capsule",
                params={"radius": 0.1, "height": 0.3},
                color=(255, 0, 0),
                material="cloth",
            )
        )

        data = char.to_dict()

        assert data["name"] == "TestChar"
        assert "skeleton" in data
        assert "shapes" in data
        assert len(data["shapes"]) == 1
        assert data["shapes"][0]["bone"] == "Spine"

    def test_from_dict(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        char.add_shape(
            ShapeAttachment(
                bone_name="Spine",
                shape_type="capsule",
                params={"radius": 0.1, "height": 0.3},
                color=(255, 0, 0),
            )
        )

        # Round-trip
        data = char.to_dict()
        char2 = CharacterDef.from_dict(data)

        assert char2.name == "TestChar"
        assert len(char2.shape_attachments) == 1
        assert char2.shape_attachments[0].bone_name == "Spine"
        assert char2.shape_attachments[0].shape_type == "capsule"

    def test_from_dict_with_palettes(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        char.add_palette("default", {"skin": "#C9A876", "hair": "#3D2817"})

        data = char.to_dict()
        char2 = CharacterDef.from_dict(data)

        assert "default" in char2.palettes
        assert char2.palettes["default"]["skin"] == "#C9A876"

    def test_humanoid_character(self):
        char = create_humanoid_character()

        assert char.name == "Humanoid Standard"
        assert len(char.shape_attachments) == 6  # Body, head, 2 arms, 2 legs

        # Check bone attachments
        bone_names = set(a.bone_name for a in char.shape_attachments)
        assert "Spine" in bone_names  # Torso
        assert "Chest" in bone_names  # Head
        assert "Arm.L" in bone_names
        assert "Arm.R" in bone_names
        assert "Leg.L" in bone_names
        assert "Leg.R" in bone_names

    def test_shape_attachment_with_transform(self):
        attachment = ShapeAttachment(
            bone_name="Head",
            shape_type="sphere",
            params={"radius": 0.1},
            translate=(0, 0.2, 0),
            scale=(1.2, 1.0, 1.0),
        )

        assert attachment.translate == (0, 0.2, 0)
        assert attachment.scale == (1.2, 1.0, 1.0)

    def test_build_shapes_with_transforms(self):
        skeleton = create_humanoid_skeleton()
        char = CharacterDef("TestChar", skeleton)

        char.add_shape(
            ShapeAttachment(
                bone_name="Spine",
                shape_type="sphere",
                params={"radius": 0.1},
                translate=(0, 0.1, 0),
                scale=(2, 1, 1),
            )
        )

        bone_positions = {"Spine": Vec3(0, 0, 0)}
        shapes = char.build_sdf_shapes(bone_positions)

        assert len(shapes) == 1
        # Shape should be transformed (scale applied)
