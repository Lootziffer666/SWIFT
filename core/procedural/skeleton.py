"""
Procedural skeleton definition and scaling for parameterized character generation.
Defines canonical humanoid skeleton and scaling transformations.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple
import math


@dataclass
class Joint:
    """A bone joint in the skeleton hierarchy."""
    name: str
    parent: Optional[str] = None
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (x, y, z) relative to parent
    bone_length: float = 1.0  # Distance to first child along bone axis


@dataclass
class SkeletonDef:
    """Complete skeleton definition with joint hierarchy."""
    root_joint: str
    joints: Dict[str, Joint] = field(default_factory=dict)

    def add_joint(self, name: str, parent: Optional[str] = None,
                  offset: Tuple[float, float, float] = (0, 0, 0),
                  bone_length: float = 1.0):
        """Add a joint to the skeleton."""
        self.joints[name] = Joint(name, parent, offset, bone_length)

    def all_joint_names(self) -> list:
        """Return all joint names in hierarchy order (root first)."""
        result = [self.root_joint]
        def visit(parent_name):
            for name, joint in self.joints.items():
                if joint.parent == parent_name:
                    result.append(name)
                    visit(name)
        visit(self.root_joint)
        return result

    def validate(self) -> Tuple[bool, str]:
        """Validate skeleton hierarchy. Returns (is_valid, error_message)."""
        if self.root_joint not in self.joints:
            return False, f"Root joint '{self.root_joint}' not in joints dict"
        for name, joint in self.joints.items():
            if joint.parent and joint.parent not in self.joints and joint.parent != self.root_joint:
                return False, f"Joint '{name}' parent '{joint.parent}' not found"
        return True, ""


def create_humanoid_skeleton() -> SkeletonDef:
    """Create canonical humanoid skeleton (Quaternius-compatible)."""
    skel = SkeletonDef(root_joint="Hips")

    # Spine chain
    skel.add_joint("Hips", parent=None, offset=(0, 0, 0), bone_length=0.15)
    skel.add_joint("Spine", parent="Hips", offset=(0, 0.15, 0), bone_length=0.12)
    skel.add_joint("Chest", parent="Spine", offset=(0, 0.12, 0), bone_length=0.10)
    skel.add_joint("Shoulder.L", parent="Chest", offset=(-0.18, 0.08, 0), bone_length=0.08)
    skel.add_joint("Shoulder.R", parent="Chest", offset=(0.18, 0.08, 0), bone_length=0.08)

    # Left arm
    skel.add_joint("Arm.L", parent="Shoulder.L", offset=(-0.08, 0, 0), bone_length=0.15)
    skel.add_joint("Forearm.L", parent="Arm.L", offset=(-0.15, 0, 0), bone_length=0.14)
    skel.add_joint("Hand.L", parent="Forearm.L", offset=(-0.14, 0, 0), bone_length=0.05)

    # Right arm
    skel.add_joint("Arm.R", parent="Shoulder.R", offset=(0.08, 0, 0), bone_length=0.15)
    skel.add_joint("Forearm.R", parent="Arm.R", offset=(0.15, 0, 0), bone_length=0.14)
    skel.add_joint("Hand.R", parent="Forearm.R", offset=(0.14, 0, 0), bone_length=0.05)

    # Left leg
    skel.add_joint("Leg.L", parent="Hips", offset=(-0.08, -0.15, 0), bone_length=0.18)
    skel.add_joint("Shin.L", parent="Leg.L", offset=(0, -0.18, 0), bone_length=0.17)
    skel.add_joint("Foot.L", parent="Shin.L", offset=(0, -0.17, 0), bone_length=0.08)

    # Right leg
    skel.add_joint("Leg.R", parent="Hips", offset=(0.08, -0.15, 0), bone_length=0.18)
    skel.add_joint("Shin.R", parent="Leg.R", offset=(0, -0.18, 0), bone_length=0.17)
    skel.add_joint("Foot.R", parent="Shin.R", offset=(0, -0.17, 0), bone_length=0.08)

    return skel


def scale_skeleton(skeleton: SkeletonDef, height_cm: float, weight_kg: float) -> SkeletonDef:
    """
    Scale skeleton parametrically by height and weight.
    Height directly scales bone lengths. Weight scales joint thicknesses (for mesh generation later).
    """
    # Standard reference: 170cm (5'7")
    ref_height = 170.0
    height_ratio = height_cm / ref_height

    # Create a copy
    scaled = SkeletonDef(root_joint=skeleton.root_joint)

    for name, joint in skeleton.joints.items():
        scaled_offset = tuple(o * height_ratio for o in joint.offset)
        scaled_bone_length = joint.bone_length * height_ratio
        scaled.add_joint(name, joint.parent, scaled_offset, scaled_bone_length)

    # Store metadata for weight-based mesh scaling (used by mesh generator)
    scaled._weight_ratio = weight_kg / 70.0  # Reference: 70kg

    return scaled


# Canonical humanoid skeleton (used throughout SWIFT)
HUMANOID_DEF = create_humanoid_skeleton()
