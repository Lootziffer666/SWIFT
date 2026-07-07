"""
Procedural skeleton generation for Blender armature and FBX export.
Transforms SkeletonDef hierarchy + SkeletonParams (height, weight) → FBX with optional IK chains.
"""
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
import os
import json
import tempfile
from core.procedural.skeleton import SkeletonDef, HUMANOID_DEF, scale_skeleton


@dataclass
class SkeletonParams:
    """Parameters for procedural skeleton generation."""
    height_cm: float
    weight_kg: float
    torso_ratio: float = 0.4  # Proportion of total height (0.3-0.5)
    limb_length_ratio: float = 1.0  # Multiplier for arm/leg lengths
    with_ik: bool = False  # Apply 2-bone IK chains to limbs
    with_mesh_bodies: bool = False  # Generate capsule mesh bodies


class SkeletonGenerator:
    """Generates procedural Blender-compatible skeletons from SkeletonDef + SkeletonParams."""

    def __init__(self, template: Optional[SkeletonDef] = None):
        """Initialize with skeleton template (defaults to HUMANOID_DEF)."""
        self.template = template or HUMANOID_DEF

    def generate(self, params: SkeletonParams, export_fbx: Optional[str] = None) -> Dict:
        """
        Generate procedural skeleton and optionally export to FBX.

        Args:
            params: SkeletonParams defining height, weight, ratios
            export_fbx: Optional path to export FBX file

        Returns:
            Dict with keys:
                - 'skeleton': scaled SkeletonDef
                - 'params': SkeletonParams used
                - 'fbx_path': path if exported, None otherwise
                - 'metadata': dict with generation metadata
        """
        # Scale template skeleton
        scaled_skeleton = scale_skeleton(self.template, params.height_cm, params.weight_kg)

        metadata = {
            "height_cm": params.height_cm,
            "weight_kg": params.weight_kg,
            "torso_ratio": params.torso_ratio,
            "limb_length_ratio": params.limb_length_ratio,
            "with_ik": params.with_ik,
            "with_mesh_bodies": params.with_mesh_bodies,
            "total_joints": len(scaled_skeleton.joints),
            "root_joint": scaled_skeleton.root_joint,
        }

        result = {
            "skeleton": scaled_skeleton,
            "params": params,
            "fbx_path": None,
            "metadata": metadata,
        }

        # Export to FBX if path provided
        if export_fbx:
            fbx_path = self._export_fbx_blender(scaled_skeleton, export_fbx, params)
            result["fbx_path"] = fbx_path

        return result

    def _export_fbx_blender(self, skeleton: SkeletonDef, out_path: str, params: SkeletonParams) -> str:
        """
        Export skeleton as FBX via Blender (requires bpy).
        Falls back to mock export if Blender unavailable.
        """
        try:
            import bpy
            return self._build_blender_armature(skeleton, out_path, params)
        except ImportError:
            # Blender not available; create placeholder FBX marker file for testing
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            # Write skeleton metadata as JSON alongside as reference
            meta_path = out_path.replace(".fbx", "_skeleton.json")
            with open(meta_path, "w") as f:
                json.dump(
                    {
                        "skeleton": {
                            "root": skeleton.root_joint,
                            "joints": {
                                name: {
                                    "parent": joint.parent,
                                    "offset": joint.offset,
                                    "bone_length": joint.bone_length,
                                }
                                for name, joint in skeleton.joints.items()
                            },
                        },
                        "params": {
                            "height_cm": params.height_cm,
                            "weight_kg": params.weight_kg,
                            "with_ik": params.with_ik,
                            "with_mesh_bodies": params.with_mesh_bodies,
                        },
                    },
                    f,
                    indent=2,
                )
            # Create a placeholder FBX file (will be replaced by real Blender export in production)
            with open(out_path, "wb") as f:
                f.write(b"FBX placeholder - replace with real Blender export\n")
            return out_path

    def _build_blender_armature(self, skeleton: SkeletonDef, out_path: str, params: SkeletonParams) -> str:
        """
        Build Blender armature from SkeletonDef hierarchy.
        Creates bones via bpy.ops, optionally adds IK chains and mesh bodies.
        """
        import bpy
        from mathutils import Vector

        # Clear scene
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

        # Create armature and object
        armature_data = bpy.data.armatures.new("CharacterArmature")
        armature_obj = bpy.data.objects.new("Armature", armature_data)
        bpy.context.collection.objects.link(armature_obj)
        bpy.context.view_layer.objects.active = armature_obj
        armature_obj.select_set(True)

        # Enter edit mode to add bones
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = armature_data.edit_bones

        # Map from joint name to bone object (for parenting)
        bone_map = {}

        # Create bones in hierarchy order
        joint_order = skeleton.all_joint_names()
        for joint_name in joint_order:
            joint = skeleton.joints[joint_name]
            bone = edit_bones.new(joint_name)
            bone_map[joint_name] = bone

            # Set bone position and length
            head = Vector(joint.offset)
            # Bone tail is along the Y axis (up) by bone_length
            tail = Vector(joint.offset) + Vector((0, joint.bone_length, 0))
            bone.head = head
            bone.tail = tail

            # Parent to parent joint if exists
            if joint.parent and joint.parent in bone_map:
                parent_bone = bone_map[joint.parent]
                bone.parent = parent_bone

        # Exit edit mode
        bpy.ops.object.mode_set(mode="OBJECT")

        # Apply optional IK chains (if with_ik=True)
        if params.with_ik:
            self._apply_ik_chains(armature_obj, skeleton)

        # Generate optional mesh bodies (if with_mesh_bodies=True)
        if params.with_mesh_bodies:
            self._generate_mesh_bodies(armature_obj, skeleton, params)

        # Export to FBX
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        bpy.ops.export_scene.fbx(
            filepath=out_path,
            use_selection=False,
            object_types={"ARMATURE", "MESH"},
            use_armature=True,
            add_leaf_bones=False,
        )

        return out_path

    def _apply_ik_chains(self, armature_obj, skeleton: SkeletonDef):
        """Apply 2-bone IK chains to legs and arms."""
        import bpy

        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode="POSE")
        pose_bones = armature_obj.pose.bones

        # Define IK chains: list of (end_effector, chain_length) tuples
        ik_chains = [
            ("Hand.L", 2),  # Forearm.L -> Arm.L
            ("Hand.R", 2),  # Forearm.R -> Arm.R
            ("Foot.L", 2),  # Shin.L -> Leg.L
            ("Foot.R", 2),  # Shin.R -> Leg.R
        ]

        for end_effector_name, chain_len in ik_chains:
            if end_effector_name not in pose_bones:
                continue

            end_effector = pose_bones[end_effector_name]

            # Add IK constraint
            ik = end_effector.constraints.new(type="IK")
            ik.chain_count = chain_len
            ik.pole_angle = 0

            # Store IK metadata in custom property (for external IK solvers)
            armature_obj[f"ik_{end_effector_name}"] = {
                "chain_length": chain_len,
                "enabled": True,
            }

        bpy.ops.object.mode_set(mode="OBJECT")

    def _generate_mesh_bodies(self, armature_obj, skeleton: SkeletonDef, params: SkeletonParams):
        """Generate simplified capsule mesh bodies for each bone."""
        import bpy
        from mathutils import Vector, Matrix

        # Simplified: create UV-sphere mesh per major joint
        # (Torso, Arm.L/R, Leg.L/R, Head if present)
        major_joints = {"Chest", "Arm.L", "Arm.R", "Leg.L", "Leg.R"}

        for joint_name in major_joints:
            if joint_name not in skeleton.joints:
                continue

            joint = skeleton.joints[joint_name]
            bone_length = joint.bone_length

            # Estimate radius from bone length and weight ratio
            weight_ratio = params.weight_kg / 70.0  # Reference 70kg
            radius = bone_length * 0.1 * (weight_ratio ** (1 / 3))  # Cube-root scaling

            # Create UV sphere
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=radius,
                location=joint.offset,
            )
            mesh_obj = bpy.context.active_object
            mesh_obj.name = f"{joint_name}_Mesh"

            # Parent mesh to armature bone
            mesh_obj.parent = armature_obj
            mesh_obj.parent_type = "BONE"
            mesh_obj.parent_bone = joint_name

    def generate_from_json(self, json_path: str, export_fbx: Optional[str] = None) -> Dict:
        """Generate skeleton from JSON params file."""
        with open(json_path, "r") as f:
            params_dict = json.load(f)
        params = SkeletonParams(**params_dict)
        return self.generate(params, export_fbx)


def generate_skeleton_cli(
    height_cm: float,
    weight_kg: float,
    export_fbx: str,
    with_ik: bool = False,
    with_mesh_bodies: bool = False,
    torso_ratio: float = 0.4,
) -> str:
    """CLI entry point for skeleton generation."""
    params = SkeletonParams(
        height_cm=height_cm,
        weight_kg=weight_kg,
        torso_ratio=torso_ratio,
        with_ik=with_ik,
        with_mesh_bodies=with_mesh_bodies,
    )
    generator = SkeletonGenerator()
    result = generator.generate(params, export_fbx)
    return result["fbx_path"]
