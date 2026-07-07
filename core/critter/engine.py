"""
Critter Crosser – engine facade.

Ties the subsystems together: a Critter owns a procedural skeleton plus its
SDF body field; the Engine advances IK limbs, flow-field NPCs, scheduling and
the twin-stick player each frame.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from core.critter.geometry import Vec3, IsometricProjection
from core.critter.ik import BoneChain, fabrik_solve
from core.critter.evolution import Skeleton, morph
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC
from core.critter.input import TwinStickController
from core.critter.scheduling import NPCSchedule


@dataclass
class Critter:
    """A procedural creature: skeleton + SDF body, animated by IK each frame."""

    name: str
    skeleton: Skeleton
    position: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    evolution: float = 0.0  # 0=larva .. 1=adult

    def body_field(self) -> Callable[[Vec3], float]:
        """Return an SDF closure describing this critter's body at its size."""
        from core.critter.sdf import sdf_sphere, sdf_union

        lengths = self.skeleton.segment_lengths or [1.0]
        radii = self.skeleton.segment_widths or [0.5] * len(lengths)
        total = sum(lengths)

        def field(p: Vec3) -> float:
            local = p - self.position
            d = 1e9
            acc = 0.0
            for i, (seg_len, rad) in enumerate(zip(lengths, radii)):
                center = Vec3(acc + seg_len / 2.0, 0.0, 0.0)
                d = sdf_union(d, sdf_sphere(local, center, max(rad, 0.05)))
                acc += seg_len
            return d

        return field


@dataclass
class Engine:
    projection: IsometricProjection = field(default_factory=IsometricProjection)
    player: TwinStickController = field(default_factory=TwinStickController)
    npcs: List[NPC] = field(default_factory=list)
    schedules: dict = field(default_factory=dict)  # npc_id -> NPCSchedule

    def add_critter_npc(self, npc: NPC, schedule: Optional[NPCSchedule] = None) -> None:
        self.npcs.append(npc)
        if schedule:
            self.schedules[npc.id] = schedule

    def update_player(self, speed: float, dt: float) -> Vec3:
        v = self.player.velocity(speed)
        # Movement in world XZ plane; y stays (ground).
        return Vec3(self.projection.scale * 0 + v.x * dt, 0.0, v.y * dt)

    def update_npcs(self, field: FlowField, speed: float, dt: float) -> None:
        for npc in self.npcs:
            npc.update(field, speed, dt)

    def active_schedule(self, npc_id: int, hour: int, minute: int):
        sched = self.schedules.get(npc_id)
        return sched.active_entry(hour, minute) if sched else None
