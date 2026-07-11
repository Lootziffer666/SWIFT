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
                - 'ik_chains': list of IK chain dicts (only if with_ik)
                - 'mesh_bodies': list of capsule mesh specs (only if with_mesh_bodies)
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

        result: Dict = {
            "skeleton": scaled_skeleton,
            "params": params,
            "fbx_path": None,
            "metadata": metadata,
            "ik_chains": [],
            "mesh_bodies": [],
        }

        # Build 2-bone IK chains for limbs when requested.
        if params.with_ik:
            result["ik_chains"] = self._compute_ik_chains(scaled_skeleton)

        # Build capsule mesh body specs for each bone when requested.
        if params.with_mesh_bodies:
            result["mesh_bodies"] = self._compute_mesh_bodies(scaled_skeleton, params)

        # Export to FBX if path provided
        if export_fbx:
            fbx_path = self._export_fbx_blender(
                scaled_skeleton, export_fbx, params,
                ik_chains=result["ik_chains"],
                mesh_bodies=result["mesh_bodies"],
            )
            result["fbx_path"] = fbx_path

        return result

    @staticmethod
    def _compute_ik_chains(skeleton: SkeletonDef) -> List[Dict]:
        """
        Compute 2-bone IK chains for the limbs of the given skeleton.

        Uses the canonical humanoid IK rig definitions. Pure (no Blender),
        so it is fully verifiable in unit tests.
        """
        from core.procedural.ik_rig import IKRigger

        rigger = IKRigger(skeleton)
        valid, msg = rigger.validate_chains()
        if not valid:
            raise ValueError(f"IK chain validation failed: {msg}")

        chains = []
        for chain in rigger.chains:
            if not chain.enabled:
                continue
            bones = rigger.get_chain_bones(chain)
            chains.append({
                "name": chain.name,
                "end_effector": chain.end_effector,
                "chain_length": chain.chain_length,
                "pole_angle": chain.pole_angle,
                "bones": bones,
            })
        return chains

    @staticmethod
    def _compute_mesh_bodies(skeleton: SkeletonDef, params: SkeletonParams) -> List[Dict]:
        """
        Compute capsule mesh body specs for every bone in the skeleton.

        Radius scales with the cube-root of the weight ratio (volume scaling),
        and length tracks the scaled bone length. Pure (no Blender), so it is
        fully verifiable in unit tests.
        """
        weight_ratio = params.weight_kg / 70.0  # Reference: 70kg
        thickness_scale = weight_ratio ** (1.0 / 3.0)

        bodies = []
        for name, joint in skeleton.joints.items():
            if joint.bone_length <= 0:
                continue
            radius = max(joint.bone_length * 0.08, 0.02) * thickness_scale
            # Cylindrical part length (caps add 2*radius). Clamp to keep valid.
            length = max(joint.bone_length - 2.0 * radius, 0.01)
            midpoint = (
                joint.offset[0],
                joint.offset[1] + joint.bone_length / 2.0,
                joint.offset[2],
            )
            bodies.append({
                "bone": name,
                "radius": radius,
                "length": length,
                "midpoint": list(midpoint),
            })
        return bodies

    def _export_fbx_blender(self, skeleton: SkeletonDef, out_path: str, params: SkeletonParams,
                             ik_chains: Optional[List[Dict]] = None,
                             mesh_bodies: Optional[List[Dict]] = None) -> Optional[str]:
        """
        Export skeleton as FBX via Blender (requires bpy, i.e. running INSIDE
        Blender's Python). Without bpy, only the verifiable JSON metadata is
        written and None is returned — callers must not treat the rig as
        renderable. (Previously a fake text file was written with an .fbx
        extension and then fed into the renderer, which cannot load it.)
        """
        try:
            import bpy  # noqa: F401
            return self._build_blender_armature(
                skeleton, out_path, params,
                ik_chains=ik_chains or [],
                mesh_bodies=mesh_bodies or [],
            )
        except ImportError:
            # bpy not available: record the rig as JSON so IK chains and mesh
            # bodies remain verifiable without Blender, but export NO fbx.
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
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
                        "ik_chains": ik_chains or [],
                        "mesh_bodies": mesh_bodies or [],
                    },
                    f,
                    indent=2,
                )
            return None

    def _build_blender_armature(self, skeleton: SkeletonDef, out_path: str, params: SkeletonParams,
                                 ik_chains: Optional[List[Dict]] = None,
                                 mesh_bodies: Optional[List[Dict]] = None) -> str:
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
            self._apply_ik_chains(armature_obj, skeleton, ik_chains or [])

        # Generate optional mesh bodies (if with_mesh_bodies=True)
        if params.with_mesh_bodies:
            self._generate_mesh_bodies(armature_obj, skeleton, params, mesh_bodies or [])

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

    def _apply_ik_chains(self, armature_obj, skeleton: SkeletonDef, ik_chains: List[Dict]):
        """
        Apply 2-bone IK chains to legs and arms in the Blender armature.

        Uses the IKRigger to apply constraints so the rig applied here matches
        exactly the chains reported in `generate()`'s result.
        """
        import bpy
        from core.procedural.ik_rig import IKRigger

        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode="POSE")
        pose_bones = armature_obj.pose.bones

        for chain in ik_chains:
            end_effector_name = chain["end_effector"]
            if end_effector_name not in pose_bones:
                continue

            end_effector = pose_bones[end_effector_name]

            # Add IK constraint
            ik = end_effector.constraints.new(type="IK")
            ik.chain_count = chain["chain_length"]
            ik.pole_angle = chain.get("pole_angle", 0.0)

            # Store IK metadata in custom property (for external IK solvers)
            armature_obj[f"ik_{chain['name']}"] = {
                "chain_length": chain["chain_length"],
                "end_effector": end_effector_name,
                "enabled": True,
            }

        bpy.ops.object.mode_set(mode="OBJECT")

    def _generate_mesh_bodies(self, armature_obj, skeleton: SkeletonDef, params: SkeletonParams,
                              mesh_bodies: List[Dict]):
        """
        Generate capsule mesh bodies for each bone in the Blender armature.

        Capsules are positioned at each bone's midpoint and oriented along the
        bone's local axis (head -> tail). Falls back to a UV sphere if the
        capsule primitive is unavailable in the running Blender version.
        """
        import bpy
        from mathutils import Vector, Quaternion

        # Bones are built along local +Y (tail = head + (0, bone_length, 0)).
        bone_dir = Vector((0.0, 1.0, 0.0))
        # Quaternion that rotates the capsule's default +Z axis onto bone_dir.
        z_axis = Vector((0.0, 0.0, 1.0))
        quat = z_axis.rotation_difference(bone_dir)

        for spec in mesh_bodies:
            name = spec["bone"]
            radius = spec["radius"]
            length = spec["length"]
            midpoint = Vector(spec["midpoint"])

            mesh_obj = None
            # Try the capsule primitive; the parameter name differs across
            # Blender versions (height vs depth), so probe defensively.
            for length_kw in ("height", "depth"):
                try:
                    bpy.ops.mesh.primitive_capsule_add(
                        radius=radius, **{length_kw: length}
                    )
                    mesh_obj = bpy.context.active_object
                    break
                except (TypeError, RuntimeError):
                    continue

            # Fallback: approximate with a UV sphere if capsule is unavailable.
            if mesh_obj is None:
                bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=midpoint)
                mesh_obj = bpy.context.active_object

            mesh_obj.name = f"{name}_Mesh"
            mesh_obj.location = midpoint
            mesh_obj.rotation_mode = "QUATERNION"
            mesh_obj.rotation_quaternion = quat

            # Parent mesh to the armature object so it stays with the rig.
            mesh_obj.parent = armature_obj

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
