"""
Critter Crosser – Studio model (framework-agnostic state + render data).

This is the single source of truth the GUI manipulates. It holds all
interactive state (creatures, evolution, IK targets, flow field, palette,
Perlin params, twin-stick) and exposes a `render()` method that returns plain,
serialisable draw data in screen space. The Qt view only paints that data, so
the model is fully testable without any GUI toolkit.
"""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.critter.geometry import Vec2, Vec3, IsometricProjection
from core.critter.sdf import sdf_sphere
from core.critter.ik import (
    BoneChain,
    solve_two_bone_law_of_cosines,
    fabrik_solve,
    ZBendConstraint,
    WobblyTower,
)
from core.critter.shaders import PerlinNoise, PaletteSwap, Color
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC
from core.critter.evolution import Skeleton, morph, breed
from core.critter.input import TwinStickController
from core.critter.engine import Critter


def _random_skeleton(rng: random.Random, segments: int = 6) -> Skeleton:
    return Skeleton(
        segment_widths=[rng.uniform(0.3, 0.8) for _ in range(segments)],
        segment_heights=[rng.uniform(0.3, 0.8) for _ in range(segments)],
        segment_lengths=[rng.uniform(0.4, 1.0) for _ in range(segments)],
        eye_count=rng.randint(1, 4),
        limb_count=rng.randint(0, 6),
        segment_count=segments,
    )


@dataclass
class RenderScene:
    creatures: List[dict] = field(default_factory=list)
    ik: dict = field(default_factory=dict)
    flow: dict = field(default_factory=dict)
    perlin: dict = field(default_factory=dict)
    stick: dict = field(default_factory=dict)


class StudioModel:
    """Mutable studio state. The GUI binds controls to these fields."""

    def __init__(self, seed: int = 1):
        self.projection = IsometricProjection(scale=26)
        self.rng = random.Random(seed)

        self.critters: List[Critter] = []
        self.selected_id: Optional[int] = None
        self._next_id = 1

        # IK playground: an editable limb chain with a draggable end-effector.
        self.ik_chain = BoneChain(
            joints=[Vec3(0, 0, 0), Vec3(1.5, 0, 0), Vec3(3, 0, 0), Vec3(4.5, 0, 0)],
            lengths=[1.5, 1.5, 1.5],
        )
        self.ik_solver = "fabrik"  # "fabrik" | "law_of_cosines"
        self.zbend = ZBendConstraint(forward_pull=0.3, backward_pull=0.3)
        self.show_z_bend = True
        self.ik_target = Vec3(4.0, 0.0, 3.0)

        # Wobbly tower (spring) for trunks/tails.
        self.wobbly = WobblyTower.create(base=Vec3(-6, 0, 0), segment_count=6, segment_length=0.6)
        self.wobbly_target = Vec3(-4.0, 0.0, 2.0)

        # Flow field.
        self.ff_config = FlowFieldConfig(width=24, height=16, default_cost=1)
        self.flow = FlowField(self.ff_config)
        self.flow_goals: List[Tuple[int, int]] = [(23, 8)]
        self.npcs: List[NPC] = []
        self.flow_play = False
        self._spawn_npcs(60)
        self.recompute_flow()

        # Palette swap (region mask colors).
        self.palette = PaletteSwap([
            Color(0.9, 0.2, 0.2, 1.0),
            Color(0.2, 0.8, 0.3, 1.0),
            Color(0.3, 0.4, 0.9, 1.0),
            Color(0.95, 0.85, 0.2, 1.0),
        ])

        # Perlin noise preview.
        self.perlin = PerlinNoise(seed=seed)
        self.perlin_mode = "scroll"   # scroll | distort | stretch
        self.perlin_scale = 0.15
        self.perlin_time = 0.0
        self.perlin_play = False
        self.perlin_grid = 48

        # Twin-stick player.
        self.stick = TwinStickController()

        # Seed a couple of starter creatures.
        self.add_critter(_random_skeleton(self.rng, 5), "Larva")
        self.add_critter(_random_skeleton(self.rng, 9), "Critter")

    # ── Critters ─────────────────────────────────────────────────────────
    def add_critter(self, skeleton: Skeleton, name: str) -> int:
        cid = self._next_id
        self._next_id += 1
        critter = Critter(name, skeleton, id=cid)
        self.critters.append(critter)
        if self.selected_id is None:
            self.selected_id = cid
        return cid

    def select(self, cid: int) -> None:
        if any(c.id == cid for c in self.critters):
            self.selected_id = cid

    def selected(self) -> Optional[Critter]:
        for c in self.critters:
            if c.id == self.selected_id:
                return c
        return self.critters[0] if self.critters else None

    def spawn_random(self, name: str = "Critter", segments: int = 6) -> int:
        return self.add_critter(_random_skeleton(self.rng, segments), name)

    def set_evolution(self, t: float) -> None:
        """Morph the selected critter between its larva and adult form."""
        # We keep a stored larva/adult per critter; default: scale current.
        c = self.selected()
        if c is None:
            return
        base = c.skeleton
        t = max(0.0, min(1.0, t))
        # Treat current skeleton as 50%; morph outward from a shrunk larva.
        larva = Skeleton(
            segment_widths=[w * 0.5 for w in base.segment_widths],
            segment_heights=[h * 0.5 for h in base.segment_heights],
            segment_lengths=[l * 0.5 for l in base.segment_lengths],
            eye_count=max(1, base.eye_count - 1),
            limb_count=max(0, base.limb_count - 2),
            segment_count=base.segment_count,
        )
        adult = Skeleton(
            segment_widths=[w * 1.4 for w in base.segment_widths],
            segment_heights=[h * 1.4 for h in base.segment_heights],
            segment_lengths=[l * 1.4 for l in base.segment_lengths],
            eye_count=base.eye_count + 1,
            limb_count=base.limb_count + 2,
            segment_count=base.segment_count,
        )
        c.skeleton = morph(larva, adult, t)

    def breed_selected(self, other_id: int) -> Optional[int]:
        a = self.selected()
        others = [c for c in self.critters if c is not a]
        if a is None or not others:
            return None
        b = others[other_id % len(others)] if others else None
        if b is None:
            return None
        child_skel = breed(a.skeleton, b.skeleton, mutation_rate=0.1, rng=self.rng)
        return self.add_critter(child_skel, f"Child of {a.name}+{b.name}")

    # ── IK ───────────────────────────────────────────────────────────────
    def set_ik_target_screen(self, sx: float, sy: float) -> None:
        world = self.projection.unproject(Vec2(sx, sy), height=0.0)
        self.ik_target = world

    def solve_ik(self) -> None:
        if self.ik_solver == "law_of_cosines" and self.ik_chain.count == 4:
            # 2-bone limb: use first + last for the analytic solve of joint 1.
            root = self.ik_chain.root
            l1 = self.ik_chain.lengths[0] + self.ik_chain.lengths[1]
            l2 = self.ik_chain.lengths[2]
            mid = solve_two_bone_law_of_cosines(root, self.ik_target, l1, l2, Vec3(0, 1, 0))
            self.ik_chain.joints[1] = mid
            self.ik_chain.joints[2] = mid
            # Place end at target.
            self.ik_chain.joints[3] = self.ik_target
        else:
            if self.show_z_bend:
                self.zbend.inject(self.ik_chain, Vec3(1, 0, 0))
            fabrik_solve(self.ik_chain, self.ik_target, iterations=20)

    def step_wobbly(self, dt: float = 1.0 / 60.0) -> None:
        self.wobbly.step(dt, self.wobbly_target)

    # ── Flow field ───────────────────────────────────────────────────────
    def _spawn_npcs(self, n: int) -> None:
        self.npcs = [
            NPC(id=i, x=self.rng.uniform(0, self.ff_config.width - 1),
                y=self.rng.uniform(0, self.ff_config.height - 1),
                on_screen=False)
            for i in range(n)
        ]

    def set_flow_goal(self, gx: int, gy: int) -> None:
        self.flow_goals = [(max(0, min(self.ff_config.width - 1, gx)),
                            max(0, min(self.ff_config.height - 1, gy)))]
        self.recompute_flow()

    def set_tile_cost(self, gx: int, gy: int, cost: int) -> None:
        self.flow.set_cost(gx, gy, cost)

    def set_tile_blocked(self, gx: int, gy: int, blocked: bool) -> None:
        self.flow.set_blocked(gx, gy, blocked)

    def recompute_flow(self) -> None:
        self.flow = FlowField(self.ff_config)
        self.flow.compute(self.flow_goals)

    def step_flow(self, dt: float = 1.0) -> None:
        for npc in self.npcs:
            npc.update(self.flow, speed=1.0, dt=dt)

    # ── Perlin ───────────────────────────────────────────────────────────
    def step_perlin(self, dt: float = 1.0 / 30.0) -> None:
        if self.perlin_play:
            self.perlin_time += dt

    def perlin_preview(self) -> List[List[float]]:
        n = self.perlin_grid
        out: List[List[float]] = []
        t = self.perlin_time
        for j in range(n):
            row = []
            for i in range(n):
                x = i * self.perlin_scale
                y = j * self.perlin_scale
                if self.perlin_mode == "scroll":
                    v = self.perlin.scrolling(x, y, t)
                elif self.perlin_mode == "distort":
                    v = self.perlin.distortion(x, y, t, amount=0.8)
                else:
                    v = self.perlin.stretched(x, y, t, scale=0.6)
                row.append(v)
            out.append(row)
        return out

    # ── Twin-stick ───────────────────────────────────────────────────────
    def set_stick(self, mx: float, my: float, ax: float, ay: float) -> None:
        self.stick.set_movement(mx, my)
        self.stick.set_aim(ax, ay)

    # ── Coordinate helpers ───────────────────────────────────────────────
    def screen_to_world(self, sx: float, sy: float, height: float = 0.0) -> Vec3:
        return self.projection.unproject(Vec2(sx, sy), height=height)

    # ── Render data (what the viewport paints) ───────────────────────────
    def render(self) -> RenderScene:
        scene = RenderScene()

        # Creatures: project body segment spheres.
        for c in self.critters:
            segs = c.skeleton.segment_lengths or [1.0]
            radii = c.skeleton.segment_widths or [0.5] * len(segs)
            bodies = []
            acc = 0.0
            base = c.position
            for seg_len, rad in zip(segs, radii):
                center = base + Vec3(acc + seg_len / 2.0, 0.0, 0.0)
                s = self.projection.project(center)
                bodies.append((s.x, s.y, max(rad, 0.05) * self.projection.scale))
                acc += seg_len
            scene.creatures.append({"name": c.name, "bodies": bodies})

        # IK chain.
        ik_pts = [self.projection.project(j) for j in self.ik_chain.joints]
        tgt = self.projection.project(self.ik_target)
        scene.ik = {
            "joints": [(p.x, p.y) for p in ik_pts],
            "target": (tgt.x, tgt.y),
            "end": (ik_pts[-1].x, ik_pts[-1].y),
        }

        # Wobbly tower.
        wob = [self.projection.project(p) for p in self.wobbly.positions]
        scene.ik["wobbly"] = [(p.x, p.y) for p in wob]

        # Flow field.
        cells = []
        for y in range(self.ff_config.height):
            for x in range(self.ff_config.width):
                d = self.flow.direction_at(x, y)
                if d.x != 0 or d.y != 0:
                    sx, sy = self._tile_center_screen(x, y)
                    cells.append((sx, sy, d.x, d.y))
        npc_pts = [self._tile_center_screen(int(n.x), int(n.y)) for n in self.npcs]
        goal_pts = [self._tile_center_screen(gx, gy) for gx, gy in self.flow_goals]
        scene.flow = {"cells": cells, "npcs": npc_pts, "goals": goal_pts,
                      "cols": self.ff_config.width, "rows": self.ff_config.height}

        # Perlin.
        scene.perlin = {"grid": self.perlin_preview()}

        # Twin-stick.
        scene.stick = {
            "move": (self.stick.movement.x, self.stick.movement.y),
            "aim": (self.stick.aim.x, self.stick.aim.y),
            "side": self.stick.can_side_step(),
        }
        return scene

    def _tile_center_screen(self, tx: int, ty: int) -> Tuple[float, float]:
        """Map a tile (col,row) to a screen position for the flow view."""
        # Use a dedicated simple top-down mapping in screen pixels.
        cell = 18.0
        return (40.0 + tx * cell, 40.0 + ty * cell)

    def screen_to_tile(self, sx: float, sy: float) -> Tuple[int, int]:
        cell = 18.0
        return (int(round((sx - 40.0) / cell)), int(round((sy - 40.0) / cell)))
