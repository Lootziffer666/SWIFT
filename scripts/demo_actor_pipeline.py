"""
End-to-end SHADED-ready actor production pipeline (demo + harness).

This script runs the COMPLETE SWIFT actor-production path end-to-end without
requiring Blender or the external SHADED runtime, so it can run in CI:

    1. Build a base actor sprite sheet, always synthetically with Pillow
       (a few frames of a simple, animated character). Real FBX renders go
       through `python main.py render`; this harness deliberately has no
       Blender dependency so CI stays deterministic.
    2. Generate SHADED world-state variant PNGs via
       core.procedural.world_states transforms (dust, aging, heat, soot, ...).
    3. Build the SpriteSheetManifest (frameRects, frames, animations,
       world_states, optional depth).
    4. Export via core.exporter.Exporter to a PNG + manifest JSON.
    5. Validate the produced manifest is SHADED.addActor-compatible:
         - required keys present (mappingVersion, sourceImage, frameRects,
           frames, animations)
         - a simulated SHADED.addActor({image, manifest, x, y, scale, anim,
           depthLayer}) receives a well-formed object (a tiny mock SHADED stub
           records the call).
    6. Validate manifest round-trip (write -> read -> write, structure equality).
    7. Print a clear summary (artifacts, frame count, fps, world states).

Run:
    python scripts/demo_actor_pipeline.py [--out DIR] [--frames N] [--fps N]

Exit code 0 on success, non-zero on validation failure.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Allow running standalone (python scripts/demo_actor_pipeline.py) as well as
# imported as a module under pytest: ensure the repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from core.exporter import Exporter
from core.sprite_sheet import SpriteSheetManifest, WorldStateRef
from core.procedural import world_states as ws


# ── synthetic base actor ──────────────────────────────────────────────────────

def build_synthetic_actor_frames(frame_count: int = 6, frame_size=(64, 96)):
    """Return a list of PIL RGBA frames depicting a tiny bobbing character.

    Each frame is a small, distinct idle animation (vertical bob + arm sway) so
    the resulting sprite sheet is visibly animated without any external tooling.
    """
    fw, fh = frame_size
    frames = []
    cx = fw // 2
    body_color = (220, 90, 70, 255)
    for i in range(frame_count):
        img = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Vertical bob: pose oscillates with the frame index.
        phase = (i / max(1, frame_count)) * 2 * 3.14159265
        bob = int(round(3 * (1 - (i % 2) * 0.6)))  # simple up/down
        sway = int(round(6 * (frame_count > 1 and (i % 2) * 2 - 1 or 0)))

        head_r = fw // 6
        head_y = fh // 5 + bob
        body_top = head_y + head_r + 2
        body_bottom = fh - 10 + bob

        # Body (rounded rectangle via ellipse + rect).
        d.ellipse(
            [cx - fw // 5, body_top, cx + fw // 5, body_bottom],
            fill=body_color,
        )
        # Head.
        d.ellipse(
            [cx - head_r, head_y - head_r, cx + head_r, head_y + head_r],
            fill=(235, 200, 170, 255),
        )
        # Eyes.
        eye_dx = max(3, head_r // 3)
        d.ellipse([cx - eye_dx - 2, head_y - 3, cx - eye_dx + 2, head_y + 3],
                  fill=(20, 20, 20, 255))
        d.ellipse([cx + eye_dx - 2, head_y - 3, cx + eye_dx + 2, head_y + 3],
                  fill=(20, 20, 20, 255))
        # Arms (sway with pose).
        d.line([cx - fw // 5, body_top + 6, cx - fw // 5 - sway, body_top + 18],
               fill=body_color, width=4)
        d.line([cx + fw // 5, body_top + 6, cx + fw // 5 + sway, body_top + 18],
               fill=body_color, width=4)
        # Legs.
        d.line([cx - 6, body_bottom, cx - 6, fh - 2 + bob], fill=body_color, width=4)
        d.line([cx + 6, body_bottom, cx + 6, fh - 2 + bob], fill=body_color, width=4)

        frames.append(img)
    return frames


# ── mock SHADED stub (records addActor calls) ─────────────────────────────────

class MockSHADED:
    """Tiny stand-in for the browser-global `window.SHADED`.

    Records every addActor call so tests/harness can assert the produced actor
    is well-formed and compatible with SHADED's expected contract.
    """

    def __init__(self):
        self.calls = []

    def addActor(self, image, manifest, x=0.0, y=0.0, scale=1.0,
                 anim=None, depthLayer=None):
        call = {
            "image": image,
            "manifest": manifest,
            "x": x,
            "y": y,
            "scale": scale,
            "anim": anim,
            "depthLayer": depthLayer,
        }
        self.calls.append(call)
        return {"id": f"actor_{len(self.calls)}", "ok": True}


# ── core pipeline ─────────────────────────────────────────────────────────────

REQUIRED_MANIFEST_KEYS = ("mappingVersion", "sourceImage", "frameRects",
                          "frames", "animations")


def build_actor_pipeline(output_dir, frame_count=6, fps=12, anim_name="idle",
                         world_state_names=("dust", "aging", "heat", "soot"),
                         intensity=0.6, depth=False):
    """Run the full actor-production path; return a summary dict.

    `output_dir` is created (cleared first) and receives the SHADED-ready actor:
      - <anim_name>_sheet.png            (packed sprite sheet)
      - <anim_name>_manifest.json        (SpriteSheetManifest v1.4.0)
      - <anim_name>_<state>.png          (world-state variant sheets)
      - <anim_name>_depth.png            (optional depth sheet)
    """
    out = Path(output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Base actor sprite sheet (always synthetic — see module docstring).
    frames = build_synthetic_actor_frames(frame_count=frame_count)

    # Pack base sheet. Exporter consumes file paths, so persist frames first.
    sheet_path = str(out / f"{anim_name}_sheet.png")
    frame_paths = []
    for i, f in enumerate(frames):
        fp = str(out / f"_f{i:02d}.png")
        f.save(fp, "PNG")
        frame_paths.append(fp)

    # Optional depth sheet (8-bit grayscale, same layout as color frames).
    depth_image_rel = None
    depth_frame_paths = None
    if depth:
        depth_frames = []
        for f in frames:
            depth_frames.append(Image.new("L", f.size, 128))
        depth_paths = []
        for i, g in enumerate(depth_frames):
            dp = str(out / f"_d{i:02d}.png")
            g.save(dp, "PNG")
            depth_paths.append(dp)
        depth_path = str(out / f"{anim_name}_depth.png")
        Exporter(depth_paths, fps=fps, depth_frame_paths=depth_paths).to_depth_sheet(depth_path)
        depth_image_rel = f"{anim_name}_depth.png"
        depth_frame_paths = depth_paths

    exporter = Exporter(frame_paths, fps=fps, depth_frame_paths=depth_frame_paths)
    exporter.to_sprite_sheet(sheet_path)

    # 2. World-state variant PNGs (apply transforms to the packed sheet).
    base_sheet = Image.open(sheet_path).convert("RGBA")
    world_state_refs = {}
    for state in world_state_names:
        transform = ws.get_world_state_transform(state)
        variant = transform(base_sheet, intensity)
        variant_rel = f"{anim_name}_{state}.png"
        variant.save(str(out / variant_rel), "PNG")
        world_state_refs[state] = WorldStateRef(
            name=state,
            transform=state,
            intensity=intensity,
            variant_path=variant_rel,
            params={"generated_by": "demo_actor_pipeline"},
        )

    # 3 + 4. Build manifest + export via Exporter.
    manifest_path = str(out / f"{anim_name}_manifest.json")
    exporter.to_manifest(
        manifest_path,
        animation_name=anim_name,
        loop=True,
        depth_image=depth_image_rel,
        world_states=world_state_refs,
    )

    summary = {
        "output_dir": str(out),
        "sheet_path": sheet_path,
        "manifest_path": manifest_path,
        "frame_count": frame_count,
        "fps": fps,
        "anim_name": anim_name,
        "world_states": list(world_state_refs.keys()),
        "world_state_variant_paths": {
            s: str(out / r.variant_path) for s, r in world_state_refs.items()
        },
        "depth_path": str(out / depth_image_rel) if depth_image_rel else None,
        "artifacts": sorted(str(p) for p in out.iterdir()),
    }
    return summary


# ── validation ────────────────────────────────────────────────────────────────

def validate_addactor_compatible(manifest_path, shaded, x=0.5, y=0.5,
                                 scale=1.0, depth_layer="mid"):
    """Assert the manifest is SHADED.addActor-compatible and invoke the stub."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    assert not missing, f"Manifest missing required keys: {missing}"

    assert manifest["mappingVersion"] == "1.4.0", "mappingVersion must be 1.4.0"
    assert isinstance(manifest["frameRects"], dict) and manifest["frameRects"]
    assert isinstance(manifest["frames"], list) and manifest["frames"]
    assert isinstance(manifest["animations"], dict) and manifest["animations"]

    anim_name = next(iter(manifest["animations"]))
    sheet_path = str(Path(manifest_path).with_name(
        manifest.get("sourceImage", {}).get("path") or f"{anim_name}_sheet.png"
    ))

    # Simulate SHADED consuming the actor.
    shaded.addActor(
        image=sheet_path,
        manifest=manifest,
        x=x,
        y=y,
        scale=scale,
        anim=anim_name,
        depthLayer=depth_layer,
    )
    assert shaded.calls, "SHADED.addActor was not called"
    call = shaded.calls[-1]
    for key in ("image", "manifest", "x", "y", "scale", "anim", "depthLayer"):
        assert key in call, f"addActor call missing {key!r}"
    assert call["anim"] == anim_name
    assert call["depthLayer"] == depth_layer
    return manifest, anim_name


def validate_manifest_roundtrip(manifest_path):
    """Write -> read -> write and assert structural equality."""
    with open(manifest_path) as f:
        first = json.load(f)
    out2 = str(Path(manifest_path).with_suffix(".roundtrip.json"))
    with open(out2, "w") as f:
        json.dump(first, f, indent=2, sort_keys=True)
    with open(out2) as f:
        second = json.load(f)
    assert first == second, "Manifest round-trip changed structure"
    return out2


# ── entry point ───────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/actor_demo",
                        help="Output directory for the SHADED-ready actor.")
    parser.add_argument("--frames", type=int, default=6,
                        help="Number of synthetic animation frames.")
    parser.add_argument("--fps", type=int, default=12,
                        help="Animation frames-per-second.")
    parser.add_argument("--anim", default="idle", help="Animation name.")
    parser.add_argument("--states", default="dust,aging,heat,soot",
                        help="Comma-separated world-state transform names.")
    parser.add_argument("--intensity", type=float, default=0.6,
                        help="World-state transform intensity [0,1].")
    parser.add_argument("--depth", action="store_true",
                        help="Also emit an optional depth sheet.")
    args = parser.parse_args(argv)

    state_names = [s.strip() for s in args.states.split(",") if s.strip()]

    print("=" * 64)
    print("SWIFT end-to-end SHADED-ready actor pipeline")
    print("=" * 64)
    print(f"base source      : synthetic Pillow character (no Blender required)")
    print(f"frames           : {args.frames}")
    print(f"fps              : {args.fps}")
    print(f"animation        : {args.anim}")
    print(f"world states     : {', '.join(state_names)} @ intensity {args.intensity}")
    print(f"depth sheet      : {'yes' if args.depth else 'no'}")
    print(f"output directory : {args.out}")
    print("-" * 64)

    summary = build_actor_pipeline(
        output_dir=args.out,
        frame_count=args.frames,
        fps=args.fps,
        anim_name=args.anim,
        world_state_names=state_names,
        intensity=args.intensity,
        depth=args.depth,
    )

    # Validate addActor compatibility with a mock SHADED stub.
    shaded = MockSHADED()
    manifest, anim_name = validate_addactor_compatible(
        summary["manifest_path"], shaded
    )
    assert len(shaded.calls) == 1

    # Validate manifest round-trip.
    roundtrip_path = validate_manifest_roundtrip(summary["manifest_path"])

    print("validation       : PASS")
    print(f"  required keys   : {', '.join(REQUIRED_MANIFEST_KEYS)}")
    print(f"  addActor call   : recorded (anim={anim_name!r}, depthLayer='mid')")
    print(f"  round-trip      : {Path(roundtrip_path).name} matches source")
    print("-" * 64)
    print("SUMMARY")
    print(f"  artifacts created : {len(summary['artifacts'])}")
    for a in summary["artifacts"]:
        print(f"    - {a}")
    print(f"  frame count       : {summary['frame_count']}")
    print(f"  fps               : {summary['fps']}")
    print(f"  world_states      : {', '.join(summary['world_states'])}")
    print(f"  manifest          : {summary['manifest_path']}")
    print("=" * 64)
    print("DONE: SHADED-ready actor emitted (PNG + manifest + variants).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
