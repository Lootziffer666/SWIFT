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

    # Phase 3: Handle procedural skeleton generation
    if args.skeleton_generator:
        from core.procedural.skeleton_generator import SkeletonParams, SkeletonGenerator
        print(f"Generating procedural skeleton (height={args.height_cm}cm, weight={args.weight_kg}kg)...")
        params = SkeletonParams(
            height_cm=args.height_cm,
            weight_kg=args.weight_kg,
            with_ik=args.with_ik,
            with_mesh_bodies=args.mesh_bodies,
        )
        generator = SkeletonGenerator()
        result = generator.generate(params, export_fbx=args.model)
        print(f"  Skeleton: {result['metadata']['total_joints']} joints")
        if result['fbx_path']:
            print(f"  FBX exported to: {result['fbx_path']}")

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
        enable_depth=args.depth_pass,
    )

    def progress(line):
        if line.strip():
            print(f"  {line}")

    print(f"Rendering {args.model} + {args.anim or 'built-in animation'}...")
    if args.depth_pass:
        print("  (with depth pass enabled)")
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

    # Phase 3: Handle palette variants
    if args.variants:
        print(f"\nGenerating palette variants: {args.variants}")
        from core.procedural.palette_swap import Palette, PaletteSwapper
        from PIL import Image

        variants_list = [v.strip() for v in args.variants.split(",")]

        # Load base sprite sheet
        base_sheet_path = out if out.endswith('.png') else out + '.png'
        if not os.path.exists(base_sheet_path):
            print(f"  ⚠️ Base sprite sheet not found: {base_sheet_path}")
        else:
            base_sheet = Image.open(base_sheet_path)
            variant_data = {}

            # Predefined variant palettes (simple RGB shifts)
            PRESET_PALETTES = {
                'red': Palette.from_hex_map({'#4169E1': '#FF6347', '#6495ED': '#FF4500', '#1E90FF': '#DC143C'}),  # Blue→Red
                'green': Palette.from_hex_map({'#4169E1': '#228B22', '#6495ED': '#32CD32', '#1E90FF': '#00AA00'}),  # Blue→Green
                'purple': Palette.from_hex_map({'#4169E1': '#9932CC', '#6495ED': '#DA70D6', '#1E90FF': '#8A2BE2'}),  # Blue→Purple
                'gold': Palette.from_hex_map({'#4169E1': '#FFD700', '#6495ED': '#FFA500', '#1E90FF': '#FF8C00'}),   # Blue→Gold
            }

            for variant_name in variants_list:
                if variant_name not in PRESET_PALETTES:
                    print(f"  ⚠️ Unknown variant: {variant_name} (skip)")
                    continue

                palette = PRESET_PALETTES[variant_name]
                swapper = PaletteSwapper(palette)
                variant_sheet = swapper.remap_frame(base_sheet)

                variant_path = out.replace('.png', f'_{variant_name}.png')
                variant_sheet.save(variant_path, 'PNG')
                variant_data[variant_name] = {
                    'path': os.path.basename(variant_path),
                    'palette': variant_name
                }
                print(f"  ✓ {variant_name}: {variant_path}")

            # Update manifest with variant metadata (if manifest exists)
            manifest_path = out.replace('.png', '_manifest.json')
            if os.path.exists(manifest_path) and variant_data:
                import json
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                manifest['variants'] = [{'name': k, 'path': v['path']} for k, v in variant_data.items()]
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f, indent=2)
                print(f"  ✓ Manifest updated with {len(variant_data)} variants")


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
    # Phase 3: Procedural character generation
    p_render.add_argument("--skeleton-generator", action="store_true", help="Generate procedural skeleton from parameters")
    p_render.add_argument("--height-cm", type=float, default=170.0, help="Character height in cm (for scaling)")
    p_render.add_argument("--weight-kg", type=float, default=70.0, help="Character weight in kg")
    p_render.add_argument("--with-ik", action="store_true", help="Apply 2-bone IK chains to limbs")
    p_render.add_argument("--mesh-bodies", action="store_true", help="Generate capsule mesh bodies for each bone")
    # Phase 3: Depth rendering
    p_render.add_argument("--depth-pass", action="store_true", help="Enable Z-buffer depth pass (8-bit grayscale)")
    # Phase 3: Palette variants
    p_render.add_argument("--variants", help="Comma-separated palette variant names (e.g. 'red,blue,green')")

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
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
