"""
SDF preview rendering: Blender-free path for `render --skeleton-generator`.

Bridges core.procedural.character_def (skeleton + attached SDF shapes) with the
pure-Python raymarcher in core.sdf to produce small RGBA idle frames, which the
standard Exporter packs into a SHADED-ready sprite sheet + manifest v1.4.0.

This is deliberately a *preview* quality path: a stylized capsule/sphere
character with simple diffuse lighting, rendered at sprite resolution. Real
FBX character renders still require Blender (core.blender_bridge); this module
exists so `--skeleton-generator` produces a usable, honest artifact on machines
without Blender instead of a placeholder file.
"""
import math
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from PIL import Image

from core.procedural.character_def import CharacterDef, create_humanoid_character
from core.procedural.skeleton import SkeletonDef, scale_skeleton
from core.sdf import Vec3
from core.sdf.composition import SDFComposite
from core.sdf.renderer import SDFRenderer


REF_HEIGHT_CM = 170.0


def bone_world_positions(skeleton: SkeletonDef) -> Dict[str, Vec3]:
    """Resolve each joint's world position by accumulating parent offsets."""
    positions: Dict[str, Vec3] = {}

    def resolve(name: str) -> Vec3:
        if name in positions:
            return positions[name]
        joint = skeleton.joints[name]
        if joint.parent and joint.parent in skeleton.joints:
            p = resolve(joint.parent)
            pos = Vec3(p.x + joint.offset[0], p.y + joint.offset[1], p.z + joint.offset[2])
        else:
            pos = Vec3(*joint.offset)
        positions[name] = pos
        return pos

    for joint_name in skeleton.joints:
        resolve(joint_name)
    return positions


def _center_positions(positions: Dict[str, Vec3], margin: float = 0.12) -> Dict[str, Vec3]:
    """Shift positions so the character's vertical extent is centered on the origin.

    `margin` approximates shape radii beyond the joint points (head sphere,
    foot capsules) so the render doesn't clip at the frame edges.
    """
    ys = [p.y for p in positions.values()]
    center_y = (max(ys) + margin + (min(ys) - margin)) / 2.0
    return {n: Vec3(p.x, p.y - center_y, p.z) for n, p in positions.items()}


def _idle_pose(positions: Dict[str, Vec3], phase: float, amplitude: float) -> Dict[str, Vec3]:
    """Apply a tiny idle animation: vertical bob + opposing arm sway.

    Pure position offsets (no joint rotation): enough to make the preview
    sheet visibly animated, deliberately subtle so silhouettes stay stable.
    Bob uses cos, sway uses sin, so no two phases of a cycle collapse onto
    the identical pose (with sin alone, phases 0 and pi both gave zero).
    """
    bob = amplitude * 0.6 * math.cos(phase)
    sway = amplitude * math.sin(phase)
    posed = {}
    for name, p in positions.items():
        y = p.y + (bob if name != "Hips" and not name.startswith(("Leg", "Shin", "Foot")) else 0.0)
        x = p.x
        if name.endswith(".L") and name.startswith(("Arm", "Forearm", "Hand")):
            x -= sway
        elif name.endswith(".R") and name.startswith(("Arm", "Forearm", "Hand")):
            x += sway
        posed[name] = Vec3(x, y, p.z)
    return posed


def _scaled_character(height_cm: float, weight_kg: float) -> Tuple[CharacterDef, float]:
    """Humanoid CharacterDef with skeleton AND shape sizes scaled to height/weight."""
    char = create_humanoid_character()
    ratio = height_cm / REF_HEIGHT_CM
    girth = (weight_kg / 70.0) ** (1.0 / 3.0)  # volume scaling, like mesh bodies
    char.skeleton = scale_skeleton(char.skeleton, height_cm, weight_kg)
    for attachment in char.shape_attachments:
        params = dict(attachment.params)
        if "radius" in params:
            params["radius"] = params["radius"] * ratio * girth
        if "height" in params:
            params["height"] = params["height"] * ratio
        if "dimensions" in params:
            params["dimensions"] = tuple(d * ratio for d in params["dimensions"])
        attachment.params = params
    return char, ratio


def render_idle_frames(
    height_cm: float = 170.0,
    weight_kg: float = 70.0,
    frame_count: int = 4,
    frame_size: Tuple[int, int] = (64, 96),
    max_steps: int = 96,
) -> List[Image.Image]:
    """Render RGBA idle frames of the procedural humanoid via SDF raymarching."""
    char, ratio = _scaled_character(height_cm, weight_kg)
    base_positions = _center_positions(bone_world_positions(char.skeleton), margin=0.12 * ratio)

    frames = []
    for i in range(frame_count):
        phase = (i / max(1, frame_count)) * 2.0 * math.pi
        posed = _idle_pose(base_positions, phase, amplitude=0.08 * ratio)
        composite = SDFComposite(char.build_sdf_shapes(posed))
        renderer = SDFRenderer(
            composite,
            resolution=frame_size,
            camera_dist=2.4 * ratio,
            camera_fov=45.0,
        )
        frames.append(
            renderer.render(max_steps=max_steps, max_distance=8.0 * ratio, transparent=True)
        )
    return frames


def export_sdf_preview(
    out_path: str,
    height_cm: float = 170.0,
    weight_kg: float = 70.0,
    frame_count: int = 4,
    fps: int = 8,
    anim_name: str = "idle",
    frame_size: Tuple[int, int] = (64, 96),
    max_steps: int = 96,
    depth_pass: bool = False,
) -> Dict[str, Optional[str]]:
    """Render the SDF preview and export sheet + canonical v1.4.0 manifest.

    Returns {"sheet_path": ..., "manifest_path": ..., "depth_path": ...} —
    the same artifact layout `render` produces via Blender, so downstream
    steps (variants, world states, SHADED.addActor) work unchanged.
    """
    from core.exporter import Exporter, export_depth_sheet

    if not out_path.endswith(".png"):
        out_path = out_path + ".png"

    frames = render_idle_frames(
        height_cm=height_cm,
        weight_kg=weight_kg,
        frame_count=frame_count,
        frame_size=frame_size,
        max_steps=max_steps,
    )

    base = os.path.splitext(out_path)[0]
    manifest_path = base + "_manifest.json"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        frame_paths = []
        for i, frame in enumerate(frames):
            p = os.path.join(tmp, f"frame_{i:04d}.png")
            frame.save(p, "PNG")
            frame_paths.append(p)

        depth_image_rel = None
        depth_frame_paths = None
        depth_path = None
        if depth_pass:
            # Flat mid-depth per frame: the preview raymarcher has no per-pixel
            # Z export yet; a constant sheet keeps the manifest contract intact.
            depth_frame_paths = []
            for i, frame in enumerate(frames):
                dp = os.path.join(tmp, f"depth_{i:04d}.png")
                Image.new("L", frame.size, 128).save(dp, "PNG")
                depth_frame_paths.append(dp)
            depth_path = base + "_depth.png"
            export_depth_sheet(depth_frame_paths, depth_path)
            depth_image_rel = os.path.basename(depth_path)

        exporter = Exporter(frame_paths, fps=fps, depth_frame_paths=depth_frame_paths)
        exporter.to_sprite_sheet(out_path)
        exporter.to_manifest(
            manifest_path,
            animation_name=anim_name,
            loop=True,
            depth_image=depth_image_rel,
        )

    return {"sheet_path": out_path, "manifest_path": manifest_path, "depth_path": depth_path}
