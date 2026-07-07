"""Tests for procedural IK: law of cosines, FABRIK, Z-bend, spring tower."""
import math
from core.critter.geometry import Vec3
from core.critter.ik import (
    BoneChain,
    solve_two_bone_law_of_cosines,
    fabrik_solve,
    ZBendConstraint,
    WobblyTower,
)


class TestLawOfCosines:
    def test_reaches_target_when_possible(self):
        root = Vec3(0, 0, 0)
        target = Vec3(2, 0, 0)
        mid = solve_two_bone_law_of_cosines(root, target, 1.2, 1.2, Vec3(0, 1, 0))
        # Distance root->mid should equal l1, mid->target should equal l2.
        assert math.isclose(mid.distance_to(root), 1.2, abs_tol=1e-3)
        assert math.isclose(mid.distance_to(target), 1.2, abs_tol=1e-3)

    def test_clamps_unreachable(self):
        root = Vec3(0, 0, 0)
        target = Vec3(10, 0, 0)
        mid = solve_two_bone_law_of_cosines(root, target, 1.0, 1.0, Vec3(0, 1, 0))
        # Should straighten toward the target, not exceed total reach.
        assert mid.distance_to(root) <= 1.0 + 1e-6


class TestFABRIK:
    def test_end_reaches_target(self):
        chain = BoneChain(
            joints=[Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(2, 0, 0), Vec3(3, 0, 0)],
            lengths=[1.0, 1.0, 1.0],
        )
        fabrik_solve(chain, Vec3(0, 0, 2.9), iterations=30)
        assert chain.end.distance_to(Vec3(0, 0, 2.9)) < 1e-2
        # Root stays anchored.
        assert chain.root == Vec3(0, 0, 0)
        # Bone lengths preserved.
        for i in range(3):
            assert math.isclose(chain.joints[i].distance_to(chain.joints[i + 1]), 1.0, abs_tol=1e-3)

    def test_unreachable_straightens(self):
        chain = BoneChain(
            joints=[Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(2, 0, 0)],
            lengths=[1.0, 1.0],
        )
        fabrik_solve(chain, Vec3(100, 0, 0), iterations=10)
        # End should point straight at the far target, length ~2.
        assert chain.end.distance_to(Vec3(0, 0, 0)) > 1.9


class TestZBendConstraint:
    def test_injects_z_bias(self):
        chain = BoneChain(
            joints=[Vec3(0, 0, 0), Vec3(0, 2, 0), Vec3(0, 1, 0), Vec3(0, 0, 2)],
            lengths=[1.0, 1.0, 1.0],
        )
        before = chain.joints[1].x
        ZBendConstraint(forward_pull=0.5, backward_pull=0.5).inject(
            chain, Vec3(1, 0, 0)
        )
        # Joint1 pulled forward (+x), joint2 pulled back (-x).
        assert chain.joints[1].x > before
        assert chain.joints[2].x < 0


class TestWobblyTower:
    def test_tip_follows_target(self):
        tower = WobblyTower.create(base=Vec3(0, 0, 0), segment_count=5, segment_length=0.5)
        for _ in range(30):
            tower.step(dt=1 / 60.0, tip_target=Vec3(1.0, 0.0, 0.0))
        # After settling, the tip should be near the target.
        tip = tower.positions[-1]
        assert tip.distance_to(Vec3(1.0, 0.0, 0.0)) < 0.6

    def test_base_pinned(self):
        tower = WobblyTower.create(base=Vec3(2, 3, 4), segment_count=4, segment_length=0.5)
        for _ in range(10):
            tower.step(dt=1 / 60.0, tip_target=Vec3(3, 3, 4))
        assert tower.positions[0] == Vec3(2, 3, 4)
