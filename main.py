"""
SWIFT – Sprite Animation AI Workflow
CLI entry point for Phase 1 (headless render).
GUI will be added in Phase 3.
"""
import argparse
import os
import sys


def cmd_render(args):
    from core.renderer import Renderer, RendererConfig, StyleParams

    config = RendererConfig(blender_path=args.blender)
    renderer = Renderer(config)

    ok, version = renderer.check()
    if not ok:
        print(f"ERROR: Blender not available: {version}")
        sys.exit(1)
    print(f"Using: {version}")

    style = StyleParams(
        width=args.width,
        height=args.height,
        fps=args.fps,
        camera_angle=args.camera,
        pixel_size=args.pixel_size,
    )

    def progress(line):
        if line.strip():
            print(f"  {line}")

    print(f"Rendering {args.model} + {args.anim or 'built-in animation'}...")
    out = renderer.render_and_export(
        char_fbx=args.model,
        anim_fbx=args.anim,
        export_path=args.output,
        export_format=args.format,
        style=style,
        progress_cb=progress,
        anim_name=args.anim_name,
    )
    print(f"Done: {out}")


def cmd_analyze(args):
    from ai.style_analyzer import StyleAnalyzer

    key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ERROR: Set ANTHROPIC_API_KEY or pass --api-key")
        sys.exit(1)

    analyzer = StyleAnalyzer(api_key=key)
    style = analyzer.analyze_sheet(args.sheet)
    print(f"Style parameters extracted from {args.sheet}:")
    print(f"  Size:         {style.width}x{style.height}px")
    print(f"  FPS:          {style.fps}")
    print(f"  Camera:       {style.camera_angle}")
    print(f"  Pixel size:   {style.pixel_size}")
    print(f"  Palette hint: {style.palette_hint}")
    print(f"  Exaggeration: {style.exaggeration}")


def cmd_mocap(args):
    from core.mocap.video_tracker import VideoTracker
    from core.mocap.bvh_exporter import export_bvh

    tracker = VideoTracker()
    print(f"Tracking {args.video}...")

    def progress(frame, total):
        if frame % 30 == 0:
            pct = int(frame / max(total, 1) * 100)
            print(f"  {pct}% ({frame}/{total} frames)")

    result = tracker.track(args.video, progress_cb=progress)
    if not result.success:
        print(f"ERROR: {result.error}")
        sys.exit(1)

    out = args.output or os.path.splitext(args.video)[0] + ".bvh"
    export_bvh(result, out)
    print(f"Done: {out} ({result.total_frames} frames at {result.fps:.1f}fps)")


def cmd_video2sprite(args):
    from core.video_to_sprite.frame_extractor import extract_frames
    from core.video_to_sprite.pixelizer import pixelize_sequence, PixelizeConfig
    from core.exporter import Exporter
    import tempfile

    frames_dir = tempfile.mkdtemp(prefix="swift_v2s_")
    print(f"Extracting frames from {args.video}...")
    result = extract_frames(
        args.video, frames_dir,
        keyframes_only=args.keyframes,
    )
    if not result.success:
        print(f"ERROR: {result.error}")
        sys.exit(1)
    print(f"  {len(result.frames)} frames extracted")

    pixel_dir = tempfile.mkdtemp(prefix="swift_px_")
    cfg = PixelizeConfig(
        target_width=args.width,
        target_height=args.height,
        palette_colors=args.colors,
        lock_palette=True,
    )
    print("Pixelizing...")
    pixel_frames = pixelize_sequence([f.path for f in result.frames], pixel_dir, cfg)

    out = args.output or os.path.splitext(args.video)[0] + "_sprites.png"
    exporter = Exporter(pixel_frames, fps=int(result.fps))
    if args.format == "gif":
        out = os.path.splitext(out)[0] + ".gif"
        exporter.to_gif(out)
    elif args.format == "frames":
        exporter.to_frames_json(os.path.splitext(out)[0] + "_frames")
    else:
        exporter.to_sprite_sheet(out)
    print(f"Done: {out}")


def cmd_spritesheet(args):
    from core.sprite_sheet import SpriteSheetManifest, SpriteSheet

    manifest = SpriteSheetManifest.from_file(args.manifest)
    sheet = SpriteSheet(args.image, manifest)

    if args.action == "list":
        print("Animations:")
        for name in sheet.list_animations():
            anim = manifest.animations[name]
            print(f"  {name:20s}  {len(anim.frames)} frames  {anim.fps}fps  {'loop' if anim.loop else 'once'}")
        print(f"\nFrames: {len(sheet.list_frame_ids())}")

    elif args.action == "export":
        if not args.anim:
            print("ERROR: --anim required for export")
            sys.exit(1)
        out = args.output or f"{args.anim}.{args.format}"
        if args.format == "gif":
            result = sheet.export_animation_gif(args.anim, out)
        else:
            result = sheet.export_animation_sheet(args.anim, out)
        print(f"Done: {result}")

    elif args.action == "extract":
        if not args.frame:
            print("ERROR: --frame required for extract")
            sys.exit(1)
        img = sheet.extract_frame(args.frame)
        out = args.output or f"{args.frame}.png"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        img.save(out)
        print(f"Done: {out} ({img.size[0]}×{img.size[1]})")


def cmd_critter(args):
    from core.critter.evolution import Skeleton, morph, breed
    from core.critter.flow_field import FlowField, FlowFieldConfig, NPC
    from core.critter.ik import fabrik_solve, BoneChain
    from core.critter.geometry import Vec3

    print("Critter Crosser engine demo")

    # Procedural evolution: larva -> adult morph.
    larva = Skeleton(
        segment_widths=[0.2] * 4, segment_heights=[0.2] * 4,
        segment_lengths=[0.3] * 4, eye_count=2, limb_count=0, segment_count=4,
    )
    adult = Skeleton(
        segment_widths=[0.6] * 8, segment_heights=[0.6] * 8,
        segment_lengths=[0.8] * 8, eye_count=2, limb_count=4, segment_count=8,
    )
    grown = morph(larva, adult, args.evolution)
    print(f"  Morphed critter @ {args.evolution:.0%}: "
          f"{grown.segment_count} segments, length {grown.normalised_length():.2f}")

    # Breeding two parents.
    child = breed(adult, grown, mutation_rate=args.mutation)
    print(f"  Bred offspring: {child.limb_count} limbs, {child.eye_count} eyes")

    # Flow-field navigation for a crowd.
    cfg = FlowFieldConfig(width=args.grid, height=1)
    field = FlowField(cfg)
    field.compute([(args.grid - 1, 0)])
    npcs = [NPC(id=i, x=0, y=0, on_screen=False) for i in range(args.npcs)]
    for _ in range(args.steps):
        for npc in npcs:
            npc.update(field, speed=1.0, dt=1.0)
    arrived = sum(1 for n in npcs if n.x >= args.grid - 2)
    print(f"  Flow-field NPCs: {arrived}/{len(npcs)} reached the goal "
          f"({field.memory_bytes()} bytes for the field)")

    # IK reach test.
    chain = BoneChain(
        joints=[Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(2, 0, 0), Vec3(3, 0, 0)],
        lengths=[1.0, 1.0, 1.0],
    )
    fabrik_solve(chain, Vec3(0, 0, 2.9), iterations=40)
    print(f"  FABRIK end-effector error: {chain.end.distance_to(Vec3(0, 0, 2.9)):.4f}")


def cmd_gui(args):
    from gui.app import run_studio
    run_studio(seed=args.seed)


def build_parser():
    parser = argparse.ArgumentParser(prog="swift", description="SWIFT Sprite Animation AI Workflow")
    sub = parser.add_subparsers(dest="command")

    # render
    p_render = sub.add_parser("render", help="Render FBX character + animation to sprite sheet")
    p_render.add_argument("--model", required=True, help="Character FBX path")
    p_render.add_argument("--anim", help="Animation FBX path")
    p_render.add_argument("--output", help="Output file path")
    p_render.add_argument("--format", choices=["sprite_sheet", "gif", "frames_json"], default="sprite_sheet")
    p_render.add_argument("--width", type=int, default=64)
    p_render.add_argument("--height", type=int, default=64)
    p_render.add_argument("--fps", type=int, default=12)
    p_render.add_argument("--camera", choices=["front", "side", "three-quarter"], default="front")
    p_render.add_argument("--pixel-size", type=int, default=4)
    p_render.add_argument("--blender", help="Path to Blender executable")
    p_render.add_argument("--anim-name", help="Animation key for the generated manifest (default: anim/model filename)")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Extract style params from a reference sheet")
    p_analyze.add_argument("sheet", help="Path to reference sheet image")
    p_analyze.add_argument("--api-key", help="Anthropic API key")

    # mocap
    p_mocap = sub.add_parser("mocap", help="Video motion capture → BVH")
    p_mocap.add_argument("video", help="Input video file")
    p_mocap.add_argument("--output", help="Output BVH path")

    # video2sprite
    p_v2s = sub.add_parser("video2sprite", help="Convert video frames to pixel art sprite sheet")
    p_v2s.add_argument("video", help="Input video file")
    p_v2s.add_argument("--output", help="Output path")
    p_v2s.add_argument("--format", choices=["sprite_sheet", "gif", "frames"], default="sprite_sheet")
    p_v2s.add_argument("--width", type=int, default=64)
    p_v2s.add_argument("--height", type=int, default=64)
    p_v2s.add_argument("--colors", type=int, default=16)
    p_v2s.add_argument("--keyframes", action="store_true", help="Extract keyframes only")

    # spritesheet
    p_ss = sub.add_parser("spritesheet", help="Work with sprite sheets + manifest")
    p_ss.add_argument("action", choices=["list", "export", "extract"])
    p_ss.add_argument("image", help="Sprite sheet PNG path")
    p_ss.add_argument("--manifest", required=True, help="Manifest JSON path")
    p_ss.add_argument("--anim", help="Animation name (for export)")
    p_ss.add_argument("--frame", help="Frame ID (for extract)")
    p_ss.add_argument("--format", choices=["sprite_sheet", "gif"], default="gif")
    p_ss.add_argument("--output", help="Output file path")

    # critter
    p_critter = sub.add_parser("critter", help="Run the Critter Crosser engine demo")
    p_critter.add_argument("--evolution", type=float, default=0.5, help="Morph t (0=larva,1=adult)")
    p_critter.add_argument("--mutation", type=float, default=0.05, help="Breeding mutation rate")
    p_critter.add_argument("--npcs", type=int, default=200, help="Number of flow-field NPCs")
    p_critter.add_argument("--grid", type=int, default=40, help="Flow-field grid width")
    p_critter.add_argument("--steps", type=int, default=60, help="Simulation steps")

    # gui
    p_gui = sub.add_parser("gui", help="Launch the Critter Crosser Studio GUI")
    p_gui.add_argument("--seed", type=int, default=1, help="Random seed for the studio")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "render": cmd_render,
        "analyze": cmd_analyze,
        "mocap": cmd_mocap,
        "video2sprite": cmd_video2sprite,
        "spritesheet": cmd_spritesheet,
        "critter": cmd_critter,
        "gui": cmd_gui,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
