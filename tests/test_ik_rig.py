"""
Tests for core/procedural/ik_rig.py IK rigging system.
"""
import pytest
import json
import tempfile
from core.procedural.ik_rig import IKChain, IKRigConfig, IKRigger
from core.procedural.skeleton import HUMANOID_DEF, SkeletonDef


class TestIKChain:
    def test_chain_defaults(self):
        chain = IKChain(name="TestArm", end_effector="Hand.L")
        assert chain.name == "TestArm"
        assert chain.end_effector == "Hand.L"
        assert chain.chain_length == 2
        assert chain.pole_angle == 0.0
        assert chain.enabled is True

    def test_chain_custom_values(self):
        chain = IKChain(
            name="LeftLeg",
            end_effector="Foot.L",
            chain_length=3,
            pole_angle=0.5,
            enabled=False,
        )
        assert chain.name == "LeftLeg"
        assert chain.chain_length == 3
        assert chain.pole_angle == 0.5
        assert chain.enabled is False


class TestIKRigger:
    def test_rigger_initialization_humanoid(self):
        rigger = IKRigger(HUMANOID_DEF)
        assert rigger.skeleton == HUMANOID_DEF
        assert len(rigger.chains) == 4  # Left arm, right arm, left leg, right leg
        assert rigger.chains[0].end_effector == "Hand.L"
        assert rigger.chains[1].end_effector == "Hand.R"
        assert rigger.chains[2].end_effector == "Foot.L"
        assert rigger.chains[3].end_effector == "Foot.R"

    def test_validate_chains_valid_humanoid(self):
        rigger = IKRigger(HUMANOID_DEF)
        valid, msg = rigger.validate_chains()
        assert valid, msg
        assert msg == ""

    def test_validate_chains_missing_end_effector(self):
        skeleton = SkeletonDef(root_joint="Root")
        skeleton.add_joint("Root")
        skeleton.add_joint("Arm", parent="Root")

        rigger = IKRigger(skeleton)
        rigger.chains = [IKChain("TestArm", "Hand.L", chain_length=2)]

        valid, msg = rigger.validate_chains()
        assert not valid
        assert "Hand.L" in msg
        assert "not found" in msg

    def test_validate_chains_insufficient_depth(self):
        skeleton = SkeletonDef(root_joint="Root")
        skeleton.add_joint("Root")
        skeleton.add_joint("Hand", parent="Root")  # Only 1 level deep

        rigger = IKRigger(skeleton)
        rigger.chains = [IKChain("ShortChain", "Hand", chain_length=2)]

        valid, msg = rigger.validate_chains()
        assert not valid
        assert "insufficient" in msg

    def test_get_chain_bones_valid(self):
        rigger = IKRigger(HUMANOID_DEF)
        chain = rigger.chains[0]  # Hand.L chain
        bones = rigger.get_chain_bones(chain)

        # Should have chain_length bones (2)
        assert len(bones) == 2
        assert bones[-1] == "Hand.L"
        # Forearm.L should be in the chain
        assert "Forearm.L" in bones

    def test_get_chain_bones_includes_end_effector(self):
        rigger = IKRigger(HUMANOID_DEF)
        chain = IKChain("TestLeg", "Foot.L", chain_length=2)
        bones = rigger.get_chain_bones(chain)

        assert "Foot.L" in bones
        assert bones[-1] == "Foot.L"

    def test_get_config_dict_structure(self):
        rigger = IKRigger(HUMANOID_DEF)
        config = rigger.get_config_dict()

        assert isinstance(config, dict)
        assert "skeleton_name" in config
        assert "chains" in config
        assert "enable_twist_correction" in config
        assert "enable_stretch" in config

        assert config["skeleton_name"] == "Hips"
        assert len(config["chains"]) == 4
        assert config["enable_twist_correction"] is True
        assert config["enable_stretch"] is False

    def test_config_dict_chain_data(self):
        rigger = IKRigger(HUMANOID_DEF)
        config = rigger.get_config_dict()

        first_chain = config["chains"][0]
        assert first_chain["name"] == "LeftArm"
        assert first_chain["end_effector"] == "Hand.L"
        assert first_chain["chain_length"] == 2
        assert first_chain["pole_angle"] == 0.0
        assert first_chain["enabled"] is True

    def test_from_dict_reconstructs_rigger(self):
        original = IKRigger(HUMANOID_DEF)
        config_dict = original.get_config_dict()

        reconstructed = IKRigger.from_dict(config_dict, HUMANOID_DEF)

        # Verify chains were reconstructed
        assert len(reconstructed.chains) == len(original.chains)
        for orig, recon in zip(original.chains, reconstructed.chains):
            assert recon.name == orig.name
            assert recon.end_effector == orig.end_effector
            assert recon.chain_length == orig.chain_length
            assert recon.pole_angle == orig.pole_angle
            assert recon.enabled == orig.enabled

    def test_from_dict_with_disabled_chains(self):
        config_dict = {
            "skeleton_name": "Hips",
            "chains": [
                {
                    "name": "LeftArm",
                    "end_effector": "Hand.L",
                    "chain_length": 2,
                    "pole_angle": 0.0,
                    "enabled": False,
                },
                {
                    "name": "RightArm",
                    "end_effector": "Hand.R",
                    "chain_length": 2,
                    "pole_angle": 0.0,
                    "enabled": True,
                },
            ],
        }

        rigger = IKRigger.from_dict(config_dict, HUMANOID_DEF)
        assert not rigger.chains[0].enabled
        assert rigger.chains[1].enabled

    def test_all_humanoid_chains_valid(self):
        """Verify all 4 humanoid IK chains are valid against HUMANOID_DEF."""
        rigger = IKRigger(HUMANOID_DEF)
        for chain in rigger.chains:
            bones = rigger.get_chain_bones(chain)
            assert len(bones) == chain.chain_length, f"Chain {chain.name} has insufficient bones"
            assert bones[-1] == chain.end_effector

    def test_pole_angle_roundtrips(self):
        """Pole angles should be preserved through config dict round-trip."""
        rigger = IKRigger(HUMANOID_DEF)
        # Modify pole angles
        rigger.chains[0].pole_angle = 0.7854  # 45 degrees
        rigger.chains[1].pole_angle = -0.7854

        config_dict = rigger.get_config_dict()
        reconstructed = IKRigger.from_dict(config_dict, HUMANOID_DEF)

        assert abs(reconstructed.chains[0].pole_angle - 0.7854) < 1e-6
        assert abs(reconstructed.chains[1].pole_angle - (-0.7854)) < 1e-6


class TestIKRigConfig:
    def test_config_creation(self):
        config = IKRigConfig(skeleton_name="TestChar")
        assert config.skeleton_name == "TestChar"
        assert len(config.chains) == 0
        assert config.enable_twist_correction is True
        assert config.enable_stretch is False

    def test_config_with_chains(self):
        chains = [
            IKChain("Arm", "Hand.L"),
            IKChain("Leg", "Foot.L"),
        ]
        config = IKRigConfig(skeleton_name="TestChar", chains=chains)
        assert len(config.chains) == 2
        assert config.chains[0].name == "Arm"
        assert config.chains[1].name == "Leg"


class TestIKIntegration:
    def test_humanoid_chains_cover_all_limbs(self):
        """Ensure all limbs have IK chains defined."""
        rigger = IKRigger(HUMANOID_DEF)
        end_effectors = {chain.end_effector for chain in rigger.chains}

        # Should have both hands and both feet
        assert "Hand.L" in end_effectors
        assert "Hand.R" in end_effectors
        assert "Foot.L" in end_effectors
        assert "Foot.R" in end_effectors

    def test_chain_hierarchy_matches_skeleton(self):
        """Verify each chain's hierarchy matches skeleton definition."""
        rigger = IKRigger(HUMANOID_DEF)
        for chain in rigger.chains:
            bones = rigger.get_chain_bones(chain)

            # Verify each bone exists and has correct parent
            for i, bone_name in enumerate(bones):
                assert bone_name in HUMANOID_DEF.joints
                bone = HUMANOID_DEF.joints[bone_name]

                if i < len(bones) - 1:
                    next_bone = bones[i + 1]
                    assert HUMANOID_DEF.joints[next_bone].parent == bone_name

    def test_rigger_with_custom_skeleton(self):
        """Test IK rigger adapts to custom skeleton hierarchy."""
        custom = SkeletonDef(root_joint="Root")
        custom.add_joint("Root")
        custom.add_joint("Arm", parent="Root", bone_length=0.5)
        custom.add_joint("Hand", parent="Arm", bone_length=0.3)

        rigger = IKRigger(custom)
        rigger.chains = [IKChain("SimpleArm", "Hand", chain_length=2)]

        valid, msg = rigger.validate_chains()
        assert valid, msg

        bones = rigger.get_chain_bones(rigger.chains[0])
        assert len(bones) == 2
        assert bones == ["Arm", "Hand"]
