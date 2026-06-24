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
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
