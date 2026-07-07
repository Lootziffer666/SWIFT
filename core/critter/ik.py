"""
Critter Crosser – procedural animation & inverse kinematics.

No keyframes: every limb is solved from math each frame so any procedurally
generated creature animates correctly.

  * Two-bone limbs (reptile legs)      -> Law of Cosines (closed form)
  * 5+ joint limbs (wings, tentacles)  -> FABRIK
  * Mammal gallop "Z-bend"             -> pre-solver constraint injection
  * Trunks / tails (wobbly tower)      -> spring physics (Verlet)
"""
import math
from dataclasses import dataclass, field
from typing import List

from core.critter.geometry import Vec3


@dataclass
class BoneChain:
    joints: List[Vec3]
    lengths: List[float]

    @property
    def root(self) -> Vec3:
        return self.joints[0]

    @property
    def end(self) -> Vec3:
        return self.joints[-1]

    @property
    def count(self) -> int:
        return len(self.joints)


def solve_two_bone_law_of_cosines(
    root: Vec3,
    target: Vec3,
    l1: float,
    l2: float,
    bend_direction: Vec3,
) -> Vec3:
    """
    Analytic IK for a 2-bone limb. Returns the middle joint (knee/elbow)
    position. Uses the Law of Cosines to find the root angle, then clamps
    unreachable targets to the maximum reach.
    """
    to_target = target - root
    dist = to_target.length
    total = l1 + l2
    if dist > total:
        dist = total * 0.999
    lo = abs(l1 - l2)
    if dist < lo:
        dist = lo + 1e-3

    cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    angle_a = math.acos(max(-1.0, min(1.0, cos_a)))

    dir_ = to_target.normalized()
    side = dir_.cross(bend_direction).normalized()
    up = side.cross(dir_).normalized()
    bend = (dir_ * math.cos(angle_a) + up * math.sin(angle_a)).normalized()
    return root + bend * l1


def fabrik_solve(
    chain: BoneChain,
    target: Vec3,
    iterations: int = 10,
    tolerance: float = 1e-2,
) -> None:
    """
    Forward And Backward Reaching Inverse Kinematics for multi-joint chains.
    Mutates `chain.joints` in place; root stays anchored.
    """
    if chain.count < 2:
        return
    root_pos = chain.root
    total_reach = sum(chain.lengths)
    if root_pos.distance_to(target) > total_reach:
        _fabrik_stretch(chain, target)
        return

    for _ in range(iterations):
        if chain.end.distance_to(target) < tolerance:
            break
        # Backward: pin end at target, pull joints back to root.
        chain.joints[-1] = target
        for i in range(chain.count - 2, -1, -1):
            d = (chain.joints[i] - chain.joints[i + 1]).normalized()
            chain.joints[i] = chain.joints[i + 1] + d * chain.lengths[i]
        # Forward: re-anchor root, push joints out to end.
        chain.joints[0] = root_pos
        for i in range(chain.count - 1):
            d = (chain.joints[i + 1] - chain.joints[i]).normalized()
            chain.joints[i + 1] = chain.joints[i] + d * chain.lengths[i]


def _fabrik_stretch(chain: BoneChain, target: Vec3) -> None:
    d = (target - chain.root).normalized()
    p = chain.root
    chain.joints[0] = p
    for i in range(len(chain.lengths)):
        p = p + d * chain.lengths[i]
        chain.joints[i + 1] = p


@dataclass
class ZBendConstraint:
    """
    Pre-solver constraint injection that forces the mammal "Z-bend" gallop.
    Generic IK bends a leg like a salamander; mammals need the knee to bend
    opposite the ankle. Each frame we nudge joint1 forward and joint2 backward
    *before* the IK solve, biasing the solution into a Z.
    """

    forward_pull: float = 0.35
    backward_pull: float = 0.35

    def inject(self, chain: BoneChain, motion: Vec3) -> None:
        if chain.count < 4:
            return  # need root + 2 interior + foot
        fwd = motion.normalized()
        chain.joints[1] = chain.joints[1] + fwd * self.forward_pull
        chain.joints[2] = chain.joints[2] - fwd * self.backward_pull


@dataclass
class WobblyTower:
    """
    Spring-physics chain ("wobbly tower") for very flexible appendages
    (trunks, tails). Point masses connected by distance constraints, integrated
    with Verlet, so inertia is simulated naturally on direction changes.
    """

    nodes: List = field(default_factory=list)  # list of dict(pos, prev, pinned)
    rest_lengths: List[float] = field(default_factory=list)
    stiffness: float = 0.5
    damping: float = 0.92

    @classmethod
    def create(
        cls,
        base: Vec3,
        segment_count: int,
        segment_length: float,
        stiffness: float = 0.5,
        damping: float = 0.92,
    ) -> "WobblyTower":
        nodes = []
        for i in range(segment_count + 1):
            p = base + Vec3(0.0, 0.0, float(i) * segment_length)
            nodes.append({"pos": p, "prev": p, "pinned": i == 0})
        return cls(
            nodes=nodes,
            rest_lengths=[segment_length] * segment_count,
            stiffness=stiffness,
            damping=damping,
        )

    def step(self, dt: float, tip_target: Vec3, gravity: Vec3 = None) -> None:
        g = gravity or Vec3(0.0, -9.8, 0.0)
        # Verlet integrate free nodes.
        for n in self.nodes[1:]:
            velocity = (n["pos"] - n["prev"]) * self.damping
            n["prev"] = n["pos"]
            n["pos"] = n["pos"] + velocity + g * (dt * dt)
        # Drive the tip toward its target.
        self.nodes[-1]["pos"] = tip_target
        # Relaxation: satisfy rest lengths, keep base pinned.
        for _ in range(8):
            self.nodes[0]["pos"] = self.nodes[0]["prev"]
            for i in range(len(self.rest_lengths)):
                a = self.nodes[i]["pos"]
                b = self.nodes[i + 1]["pos"]
                delta = b - a
                dist = max(delta.length, 1e-4)
                diff = (dist - self.rest_lengths[i]) / dist
                correction = delta * (0.5 * self.stiffness * diff)
                if i == 0:
                    # Base is pinned: only move the child node.
                    self.nodes[i + 1]["pos"] = b - correction
                else:
                    self.nodes[i]["pos"] = a + correction
                    self.nodes[i + 1]["pos"] = b - correction
        # Re-anchor the base exactly after the final constraint pass.
        self.nodes[0]["pos"] = self.nodes[0]["prev"]

    @property
    def positions(self) -> List[Vec3]:
        return [n["pos"] for n in self.nodes]
