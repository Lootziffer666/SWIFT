"""
Critter Crosser – procedural creature engine for SWIFT.

Implements the systems described in the technical concept:
  * Fake-3D isometric projection + Signed Distance Fields (geometry, sdf)
  * Procedural IK (law of cosines, FABRIK, Z-bend, spring)        (ik)
  * Perlin-noise VFX, palette swap, GPU particles, transparency   (shaders)
  * Flow-field pathfinding for thousands of NPCs                  (flow_field)
  * Procedural evolution & breeding (LERP, clamping, mutation)    (evolution)
  * Twin-stick input + human-readable NPC scheduling              (input, scheduling)
"""
from core.critter.geometry import Vec2, Vec3, IsometricProjection
from core.critter.sdf import (
    sdf_sphere,
    sdf_capsule,
    sdf_box,
    sdf_union,
    sdf_smooth_union,
    sdf_sinusoidal_displace,
    BoundingBox,
    SDFRenderer,
)
from core.critter.ik import (
    BoneChain,
    solve_two_bone_law_of_cosines,
    fabrik_solve,
    ZBendConstraint,
    WobblyTower,
)
from core.critter.shaders import (
    PerlinNoise,
    PaletteSwap,
    Color,
    ParticleSystem,
    sort_back_to_front,
)
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC
from core.critter.evolution import Skeleton, morph, breed
from core.critter.input import TwinStickController
from core.critter.scheduling import NPCSchedule, ScheduleEntry
from core.critter.engine import Critter, Engine

__all__ = [
    "Vec2", "Vec3", "IsometricProjection",
    "sdf_sphere", "sdf_capsule", "sdf_box", "sdf_union",
    "sdf_smooth_union", "sdf_sinusoidal_displace", "BoundingBox", "SDFRenderer",
    "BoneChain", "solve_two_bone_law_of_cosines", "fabrik_solve",
    "ZBendConstraint", "WobblyTower",
    "PerlinNoise", "PaletteSwap", "Color", "ParticleSystem", "sort_back_to_front",
    "FlowField", "FlowFieldConfig", "NPC",
    "Skeleton", "morph", "breed",
    "TwinStickController",
    "NPCSchedule", "ScheduleEntry",
    "Critter", "Engine",
]
