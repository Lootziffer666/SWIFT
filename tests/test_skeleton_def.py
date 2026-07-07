"""
Tests for core/procedural/skeleton.py skeleton definition and scaling.
"""
import pytest
from core.procedural.skeleton import (
    Joint, SkeletonDef, HUMANOID_DEF, create_humanoid_skeleton, scale_skeleton
)


class TestSkeletonDef:
    def test_skeleton_add_joint(self):
        skel = SkeletonDef(root_joint="Root")
        skel.add_joint("Root")
        skel.add_joint("Child", parent="Root", offset=(0, 1, 0), bone_length=0.5)

        assert "Root" in skel.joints
        assert "Child" in skel.joints
        assert skel.joints["Child"].parent == "Root"
        assert skel.joints["Child"].offset == (0, 1, 0)

    def test_skeleton_validate(self):
        skel = SkeletonDef(root_joint="Root")
        skel.add_joint("Root")
        skel.add_joint("Child", parent="Root")

        is_valid, msg = skel.validate()
        assert is_valid
        assert msg == ""

    def test_skeleton_validate_missing_root(self):
        skel = SkeletonDef(root_joint="Missing")
        is_valid, msg = skel.validate()
        assert not is_valid

    def test_skeleton_hierarchy_order(self):
        skel = SkeletonDef(root_joint="Hips")
        skel.add_joint("Hips")
        skel.add_joint("Leg", parent="Hips")
        skel.add_joint("Foot", parent="Leg")

        joints = skel.all_joint_names()
        assert joints[0] == "Hips"
        assert "Leg" in joints
        assert "Foot" in joints


class TestHumanoidSkeleton:
    def test_humanoid_def_valid(self):
        is_valid, msg = HUMANOID_DEF.validate()
        assert is_valid, msg

    def test_humanoid_has_key_joints(self):
        keys = set(HUMANOID_DEF.joints.keys())
        required = {"Hips", "Spine", "Chest", "Arm.L", "Leg.L", "Hand.L"}
        assert required.issubset(keys)

    def test_humanoid_bone_lengths_positive(self):
        for name, joint in HUMANOID_DEF.joints.items():
            assert joint.bone_length > 0, f"Joint {name} has non-positive bone_length"


class TestSkeletonScaling:
    def test_scale_skeleton_by_height(self):
        tall = scale_skeleton(HUMANOID_DEF, height_cm=200, weight_kg=70)
        short = scale_skeleton(HUMANOID_DEF, height_cm=150, weight_kg=70)

        # Taller skeleton should have longer bones
        tall_spine_len = tall.joints["Spine"].bone_length
        short_spine_len = short.joints["Spine"].bone_length
        assert tall_spine_len > short_spine_len

    def test_scale_skeleton_preserves_proportions(self):
        ref = HUMANOID_DEF
        scaled = scale_skeleton(HUMANOID_DEF, height_cm=170, weight_kg=70)

        # At reference height, proportions should be preserved
        for name, joint in ref.joints.items():
            # Offset should scale proportionally
            for i in range(3):
                expected = joint.offset[i] * (170.0 / 170.0)
                actual = scaled.joints[name].offset[i]
                assert abs(expected - actual) < 1e-6

    def test_scale_skeleton_hierarchy_preserved(self):
        scaled = scale_skeleton(HUMANOID_DEF, height_cm=180, weight_kg=80)

        # Parent-child relationships should be preserved
        for name, joint in scaled.joints.items():
            assert name in HUMANOID_DEF.joints
            assert scaled.joints[name].parent == HUMANOID_DEF.joints[name].parent
