"""
Non-Blender unit tests for procedural skeleton math:
- height/weight -> proportions (bone scaling)
- joint counts
- IK 2-bone chain construction
- capsule mesh body sizing

These run without Blender (the generator falls back to a mock FBX export).
"""
import os
import json
import tempfile

import pytest

from core.procedural.skeleton_generator import SkeletonParams, SkeletonGenerator
from core.procedural.skeleton import HUMANOID_DEF, scale_skeleton


def _gen(**overrides):
    params = SkeletonParams(
        height_cm=overrides.pop("height_cm", 170.0),
        weight_kg=overrides.pop("weight_kg", 70.0),
        **overrides,
    )
    gen = SkeletonGenerator()
    return gen.generate(params)


class TestProportions:
    def test_height_scales_bone_lengths_linearly(self):
        short = _gen(height_cm=150)
        tall = _gen(height_cm=200)
        ratio = 200.0 / 150.0
        s = short["skeleton"].joints["Spine"].bone_length
        t = tall["skeleton"].joints["Spine"].bone_length
        assert abs((t / s) - ratio) < 1e-6

    def test_reference_height_preserves_proportions(self):
        scaled = _gen(height_cm=170)["skeleton"]
        for name, joint in HUMANOID_DEF.joints.items():
            assert abs(scaled.joints[name].offset[1] - joint.offset[1]) < 1e-9

    def test_weight_does_not_change_bone_length(self):
        light = _gen(weight_kg=50)["skeleton"]
        heavy = _gen(weight_kg=100)["skeleton"]
        for name in HUMANOID_DEF.joints:
            assert abs(
                light.joints[name].bone_length - heavy.joints[name].bone_length
            ) < 1e-9


class TestJointCounts:
    def test_joint_count_matches_template(self):
        result = _gen()
        assert result["metadata"]["total_joints"] == len(HUMANOID_DEF.joints)
        assert result["skeleton"].root_joint == "Hips"

    def test_all_joints_have_positive_length(self):
        result = _gen(height_cm=210, weight_kg=120)
        for name, joint in result["skeleton"].joints.items():
            assert joint.bone_length > 0, f"{name} has non-positive length"


class TestIKChains:
    def test_with_ik_false_yields_no_chains(self):
        result = _gen()
        assert result["ik_chains"] == []

    def test_with_ik_true_builds_four_limb_chains(self):
        result = _gen(with_ik=True)
        chains = result["ik_chains"]
        assert len(chains) == 4
        end_effectors = {c["end_effector"] for c in chains}
        assert end_effectors == {"Hand.L", "Hand.R", "Foot.L", "Foot.R"}

    def test_ik_chains_are_two_bone(self):
        result = _gen(with_ik=True)
        for chain in result["ik_chains"]:
            assert chain["chain_length"] == 2
            assert len(chain["bones"]) == 2
            assert chain["bones"][-1] == chain["end_effector"]

    def test_ik_chain_hierarchy_is_correct(self):
        result = _gen(with_ik=True)
        for chain in result["ik_chains"]:
            bones = chain["bones"]
            for i in range(len(bones) - 1):
                child = HUMANOID_DEF.joints[bones[i + 1]]
                assert child.parent == bones[i]

    def test_ik_chains_recorded_in_mock_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            fbx = os.path.join(tmp, "char.fbx")
            result = _gen(with_ik=True)
            gen = SkeletonGenerator()
            gen.generate(result["params"], export_fbx=fbx)
            meta_path = fbx.replace(".fbx", "_skeleton.json")
            assert os.path.exists(meta_path)
            with open(meta_path) as f:
                meta = json.load(f)
            assert len(meta["ik_chains"]) == 4


class TestMeshBodies:
    def test_with_mesh_bodies_false_yields_no_bodies(self):
        result = _gen()
        assert result["mesh_bodies"] == []

    def test_mesh_body_per_bone(self):
        result = _gen(with_mesh_bodies=True)
        expected = sum(1 for j in HUMANOID_DEF.joints.values() if j.bone_length > 0)
        assert len(result["mesh_bodies"]) == expected

    def test_mesh_body_length_tracks_bone(self):
        result = _gen(with_mesh_bodies=True)
        skel = result["skeleton"]
        by_bone = {b["bone"]: b for b in result["mesh_bodies"]}
        for name, joint in skel.joints.items():
            if joint.bone_length <= 0:
                continue
            spec = by_bone[name]
            assert spec["length"] <= joint.bone_length
            assert abs(spec["midpoint"][1] - (joint.offset[1] + joint.bone_length / 2)) < 1e-9

    def test_heavier_weight_yields_larger_radius(self):
        light = _gen(with_mesh_bodies=True, weight_kg=50)["mesh_bodies"]
        heavy = _gen(with_mesh_bodies=True, weight_kg=120)["mesh_bodies"]
        light_r = {b["bone"]: b["radius"] for b in light}
        heavy_r = {b["bone"]: b["radius"] for b in heavy}
        for name in light_r:
            assert heavy_r[name] > light_r[name]

    def test_mesh_bodies_recorded_in_mock_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            fbx = os.path.join(tmp, "char.fbx")
            gen = SkeletonGenerator()
            gen.generate(
                SkeletonParams(height_cm=170, weight_kg=70, with_mesh_bodies=True),
                export_fbx=fbx,
            )
            meta_path = fbx.replace(".fbx", "_skeleton.json")
            with open(meta_path) as f:
                meta = json.load(f)
            assert len(meta["mesh_bodies"]) > 0


class TestNonDestructiveExport:
    """Ensure generate writes only to the path it is given (never clobbers a sibling)."""

    def test_export_path_is_exactly_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.path.join(tmp, "hero.fbx")
            with open(original, "wb") as f:
                f.write(b"ORIGINAL MODEL DATA")
            derived = os.path.join(tmp, "hero_procedural.fbx")

            gen = SkeletonGenerator()
            result = gen.generate(
                SkeletonParams(height_cm=180, weight_kg=80, with_ik=True, with_mesh_bodies=True),
                export_fbx=derived,
            )
            assert result["fbx_path"] == derived
            assert os.path.exists(derived)
            with open(original, "rb") as f:
                assert f.read() == b"ORIGINAL MODEL DATA"
