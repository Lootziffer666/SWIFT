"""
IK (Inverse Kinematics) rigging for procedurally-generated skeletons.
Applies 2-bone IK chains to limbs for natural constraint-based posing.
Requires Blender (bpy) for actual rigging; provides validation and configuration otherwise.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from core.procedural.skeleton import SkeletonDef, Joint


@dataclass
class IKChain:
    """Definition of a 2-bone IK chain (e.g., upper_arm → forearm → hand)."""

    name: str  # e.g., "LeftArm"
    end_effector: str  # Terminal joint (e.g., "Hand.L")
    chain_length: int = 2  # Number of bones in chain (typically 2)
    pole_angle: float = 0.0  # Radians, controls limb bending direction
    pole_target: Optional[str] = None  # Optional pole target joint for bending direction
    enabled: bool = True


@dataclass
class IKRigConfig:
    """Complete IK rigging configuration for a skeleton."""

    skeleton_name: str
    chains: List[IKChain] = field(default_factory=list)
    enable_twist_correction: bool = True  # Prevent twist accumulation
    enable_stretch: bool = False  # Allow limb stretching to reach targets


class IKRigger:
    """Applies IK chains to skeleton armatures in Blender."""

    # Canonical IK chain definitions for humanoid skeletons
    HUMANOID_CHAINS = [
        IKChain("LeftArm", "Hand.L", chain_length=2, pole_angle=0.0),
        IKChain("RightArm", "Hand.R", chain_length=2, pole_angle=0.0),
        IKChain("LeftLeg", "Foot.L", chain_length=2, pole_angle=0.0),
        IKChain("RightLeg", "Foot.R", chain_length=2, pole_angle=0.0),
    ]

    def __init__(self, skeleton: SkeletonDef):
        """Initialize IK rigger for a skeleton."""
        self.skeleton = skeleton
        self.chains = self.HUMANOID_CHAINS.copy()

    def validate_chains(self) -> Tuple[bool, str]:
        """Validate that all chain end-effectors exist in skeleton."""
        for chain in self.chains:
            if not chain.enabled:
                continue
            if chain.end_effector not in self.skeleton.joints:
                return (
                    False,
                    f"IK chain '{chain.name}': end effector '{chain.end_effector}' not found in skeleton",
                )
            # Check chain depth
            joint = self.skeleton.joints[chain.end_effector]
            count = 0
            while joint.parent and count < chain.chain_length:
                if joint.parent not in self.skeleton.joints:
                    return (
                        False,
                        f"IK chain '{chain.name}': parent '{joint.parent}' not found",
                    )
                joint = self.skeleton.joints[joint.parent]
                count += 1
            if count < chain.chain_length:
                return (
                    False,
                    f"IK chain '{chain.name}': insufficient parent joints (need {chain.chain_length}, found {count})",
                )
        return True, ""

    def get_chain_bones(self, chain: IKChain) -> List[str]:
        """Get bone names in IK chain (from end effector up the hierarchy)."""
        bones = [chain.end_effector]
        joint = self.skeleton.joints[chain.end_effector]

        for _ in range(chain.chain_length - 1):
            if not joint.parent:
                break
            joint = self.skeleton.joints[joint.parent]
            bones.insert(0, joint.name)

        return bones

    def apply_ik_chains_blender(self, armature_obj) -> bool:
        """
        Apply IK constraints to armature object in Blender.
        Returns True if successful, False if Blender not available.
        """
        try:
            import bpy
        except ImportError:
            return False

        # Validate before applying
        valid, msg = self.validate_chains()
        if not valid:
            print(f"IK validation failed: {msg}")
            return False

        # Enter pose mode
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode="POSE")
        pose_bones = armature_obj.pose.bones

        for chain in self.chains:
            if not chain.enabled:
                continue

            end_eff_name = chain.end_effector
            if end_eff_name not in pose_bones:
                print(f"Warning: End effector '{end_eff_name}' not in pose bones")
                continue

            end_effector = pose_bones[end_eff_name]

            # Add IK constraint
            ik_constraint = end_effector.constraints.new(type="IK")
            ik_constraint.chain_count = chain.chain_length
            ik_constraint.pole_angle = chain.pole_angle

            # Set pole target if specified
            if chain.pole_target and chain.pole_target in pose_bones:
                pole_bone = pose_bones[chain.pole_target]
                ik_constraint.pole_target = None  # Would set to empty object in production

            # Store metadata in armature custom properties
            armature_obj[f"ik_{chain.name}_enabled"] = True
            armature_obj[f"ik_{chain.name}_chain_length"] = chain.chain_length
            armature_obj[f"ik_{chain.name}_pole_angle"] = chain.pole_angle
            armature_obj[f"ik_{chain.name}_end_effector"] = end_eff_name

        bpy.ops.object.mode_set(mode="OBJECT")
        return True

    def get_config_dict(self) -> Dict:
        """Export configuration as dictionary for JSON serialization."""
        return {
            "skeleton_name": self.skeleton.root_joint,
            "chains": [
                {
                    "name": chain.name,
                    "end_effector": chain.end_effector,
                    "chain_length": chain.chain_length,
                    "pole_angle": chain.pole_angle,
                    "enabled": chain.enabled,
                }
                for chain in self.chains
            ],
            "enable_twist_correction": True,
            "enable_stretch": False,
        }

    @staticmethod
    def from_dict(data: Dict, skeleton: SkeletonDef) -> "IKRigger":
        """Reconstruct IK rigger from configuration dict."""
        rigger = IKRigger(skeleton)
        rigger.chains = []
        for chain_data in data.get("chains", []):
            chain = IKChain(
                name=chain_data["name"],
                end_effector=chain_data["end_effector"],
                chain_length=chain_data.get("chain_length", 2),
                pole_angle=chain_data.get("pole_angle", 0.0),
                enabled=chain_data.get("enabled", True),
            )
            rigger.chains.append(chain)
        return rigger


def apply_ik_to_fbx(fbx_path: str, ik_config: Dict) -> bool:
    """
    Apply IK configuration to an existing FBX file.
    Requires Blender and will modify the FBX in-place.
    """
    try:
        import bpy
    except ImportError:
        print("Warning: Blender not available, IK rigging skipped")
        return False

    # Import FBX
    bpy.ops.import_scene.fbx(filepath=fbx_path)

    # Find armature object
    armature_obj = None
    for obj in bpy.context.selected_objects:
        if obj.type == "ARMATURE":
            armature_obj = obj
            break

    if not armature_obj:
        print(f"No armature found in {fbx_path}")
        return False

    # Reconstruct skeleton from armature
    skeleton = _skeleton_from_blender_armature(armature_obj)
    rigger = IKRigger.from_dict(ik_config, skeleton)

    # Apply IK chains
    rigger.apply_ik_chains_blender(armature_obj)

    # Export back to FBX
    bpy.ops.export_scene.fbx(
        filepath=fbx_path,
        use_selection=False,
        object_types={"ARMATURE", "MESH"},
        use_armature=True,
    )

    return True


def _skeleton_from_blender_armature(armature_obj) -> SkeletonDef:
    """Reconstruct SkeletonDef from Blender armature object."""
    from core.procedural.skeleton import SkeletonDef

    bones = armature_obj.data.bones

    # Find root bone
    root_name = None
    for bone in bones:
        if not bone.parent:
            root_name = bone.name
            break

    if not root_name:
        root_name = bones[0].name if bones else "Root"

    skeleton = SkeletonDef(root_joint=root_name)

    # Add all bones
    for bone in bones:
        offset = tuple(bone.head.to_tuple())
        bone_length = bone.length
        parent_name = bone.parent.name if bone.parent else None

        skeleton.add_joint(bone.name, parent_name, offset, bone_length)

    return skeleton
