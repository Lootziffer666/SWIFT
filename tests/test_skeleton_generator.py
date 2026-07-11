"""
Tests for core/procedural/skeleton_generator.py procedural skeleton generation.
"""
import pytest
import tempfile
import os
import json
from core.procedural.skeleton_generator import SkeletonParams, SkeletonGenerator
from core.procedural.skeleton import HUMANOID_DEF, scale_skeleton


class TestSkeletonParams:
    def test_params_defaults(self):
        params = SkeletonParams(height_cm=170, weight_kg=70)
        assert params.height_cm == 170
        assert params.weight_kg == 70
        assert params.torso_ratio == 0.4
        assert params.limb_length_ratio == 1.0
        assert params.with_ik is False
        assert params.with_mesh_bodies is False

    def test_params_custom_values(self):
        params = SkeletonParams(
            height_cm=190,
            weight_kg=90,
            torso_ratio=0.35,
            limb_length_ratio=1.1,
            with_ik=True,
            with_mesh_bodies=True,
        )
        assert params.height_cm == 190
        assert params.weight_kg == 90
        assert params.torso_ratio == 0.35
        assert params.limb_length_ratio == 1.1
        assert params.with_ik is True
        assert params.with_mesh_bodies is True


class TestSkeletonGenerator:
    def test_generator_initialization(self):
        gen = SkeletonGenerator()
        assert gen.template == HUMANOID_DEF

    def test_generator_with_custom_template(self):
        from core.procedural.skeleton import SkeletonDef

        custom = SkeletonDef(root_joint="Root")
        gen = SkeletonGenerator(template=custom)
        assert gen.template == custom

    def test_generate_returns_valid_structure(self):
        params = SkeletonParams(height_cm=170, weight_kg=70)
        gen = SkeletonGenerator()
        result = gen.generate(params)

        assert isinstance(result, dict)
        assert "skeleton" in result
        assert "params" in result
        assert "fbx_path" in result
        assert "metadata" in result
        assert result["fbx_path"] is None  # No FBX path without export_fbx arg

    def test_generate_scales_skeleton_correctly(self):
        params = SkeletonParams(height_cm=200, weight_kg=70)
        gen = SkeletonGenerator()
        result = gen.generate(params)

        scaled_skeleton = result["skeleton"]
        # At 200cm (vs 170cm reference), bones should be ~1.176x longer
        scale_factor = 200.0 / 170.0

        # Check a few key joints
        hips_bone_len = scaled_skeleton.joints["Hips"].bone_length
        ref_hips_bone_len = HUMANOID_DEF.joints["Hips"].bone_length
        expected = ref_hips_bone_len * scale_factor

        assert abs(hips_bone_len - expected) < 1e-6

    def test_generate_preserves_hierarchy(self):
        params = SkeletonParams(height_cm=150, weight_kg=50)
        gen = SkeletonGenerator()
        result = gen.generate(params)

        scaled_skeleton = result["skeleton"]

        # Parent relationships must match original
        for name, joint in scaled_skeleton.joints.items():
            assert name in HUMANOID_DEF.joints
            assert joint.parent == HUMANOID_DEF.joints[name].parent

    def test_generate_metadata_matches_params(self):
        params = SkeletonParams(
            height_cm=180,
            weight_kg=75,
            torso_ratio=0.42,
            limb_length_ratio=1.05,
            with_ik=True,
        )
        gen = SkeletonGenerator()
        result = gen.generate(params)

        metadata = result["metadata"]
        assert metadata["height_cm"] == 180
        assert metadata["weight_kg"] == 75
        assert metadata["torso_ratio"] == 0.42
        assert metadata["limb_length_ratio"] == 1.05
        assert metadata["with_ik"] is True
        assert metadata["total_joints"] == len(HUMANOID_DEF.joints)
        assert metadata["root_joint"] == "Hips"

    def test_generate_with_fbx_export_without_blender(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fbx_path = os.path.join(tmpdir, "test_char.fbx")
            params = SkeletonParams(height_cm=170, weight_kg=70)
            gen = SkeletonGenerator()
            result = gen.generate(params, export_fbx=fbx_path)

            # Without bpy no FBX may be produced — especially not a fake text
            # file with an .fbx extension (the old placeholder broke renders).
            assert result["fbx_path"] is None
            assert not os.path.exists(fbx_path)

            # The verifiable skeleton metadata JSON is still written.
            meta_path = fbx_path.replace(".fbx", "_skeleton.json")
            assert os.path.exists(meta_path)

            # Verify metadata structure
            with open(meta_path, "r") as f:
                meta = json.load(f)
            assert "skeleton" in meta
            assert "params" in meta
            assert meta["skeleton"]["root"] == "Hips"
            assert len(meta["skeleton"]["joints"]) > 0

    def test_generate_multiple_heights_scale_independently(self):
        params_short = SkeletonParams(height_cm=150, weight_kg=60)
        params_tall = SkeletonParams(height_cm=200, weight_kg=90)
        gen = SkeletonGenerator()

        result_short = gen.generate(params_short)
        result_tall = gen.generate(params_tall)

        short_spine_len = result_short["skeleton"].joints["Spine"].bone_length
        tall_spine_len = result_tall["skeleton"].joints["Spine"].bone_length

        # Tall should be longer
        assert tall_spine_len > short_spine_len

        # Verify ratio matches height ratio
        height_ratio = 200.0 / 150.0
        expected_ratio = tall_spine_len / short_spine_len
        assert abs(expected_ratio - height_ratio) < 0.01

    def test_generate_from_json_loads_params(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            params_json = os.path.join(tmpdir, "params.json")
            params_dict = {
                "height_cm": 185,
                "weight_kg": 85,
                "torso_ratio": 0.38,
                "with_ik": True,
            }
            with open(params_json, "w") as f:
                json.dump(params_dict, f)

            gen = SkeletonGenerator()
            result = gen.generate_from_json(params_json)

            assert result["metadata"]["height_cm"] == 185
            assert result["metadata"]["weight_kg"] == 85
            assert result["metadata"]["torso_ratio"] == 0.38
            assert result["metadata"]["with_ik"] is True

    def test_generate_validates_joint_counts(self):
        params = SkeletonParams(height_cm=170, weight_kg=70)
        gen = SkeletonGenerator()
        result = gen.generate(params)

        # Must have same joint count as template
        assert result["metadata"]["total_joints"] == len(HUMANOID_DEF.joints)
        assert result["skeleton"].root_joint == HUMANOID_DEF.root_joint

    def test_skeleton_all_bones_positive_length(self):
        params = SkeletonParams(height_cm=200, weight_kg=100)
        gen = SkeletonGenerator()
        result = gen.generate(params)

        for name, joint in result["skeleton"].joints.items():
            assert joint.bone_length > 0, f"Joint {name} has non-positive bone_length"
