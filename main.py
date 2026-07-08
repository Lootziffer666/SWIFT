"""
SWIFT – Sprite Animation AI Workflow
CLI entry point for Phase 1 (headless render).
The PySide6 GUI lives in gui/app.py and is launched via `swift gui`.
"""
import argparse
import json
import os
import sys


# Exit codes (SWIFT <-> ANVIL orchestration contract, see docs/ORCHESTRATION.md)
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_MISSING_INPUT = 2
EXIT_TOOL_MISSING = 3


class InputMissingError(Exception):
    """Raised when a required input file/value is missing (exit code 2)."""


class ToolMissingError(Exception):
    """Raised when an external tool (e.g. Blender) is missing (exit code 3)."""


class Reporter:
    """Routes human-readable output.

    In JSON mode all human/progress text goes to STDERR so that STDOUT stays
    reserved for the single machine-readable JSON summary object.
    """

    def __init__(self, json_mode: bool):
        self.json_mode = json_mode

    def say(self, msg: str):
        if self.json_mode:
            print(msg, file=sys.stderr)
        else:
            print(msg)

    def progress(self, line: str):
        if line and line.strip():
            print(f"  {line}", file=sys.stderr)


def _emit_success(reporter: Reporter, command: str, **fields):
    summary = {"status": "success", "command": command}
    summary.update(fields)
    print(json.dumps(summary, indent=2))


def _emit_error(reporter: Reporter, message: str, code: int):
    if reporter.json_mode:
        print(json.dumps({"status": "error", "error": message}), file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def _read_manifest_raw(path: str):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _build_render_summary(args, sheet_path: str) -> dict:
    base = os.path.splitext(sheet_path)[0]
    manifest_path = base + "_manifest.json"

    artifacts = [{"type": "sprite_sheet", "path": sheet_path}]
    depth_path = None
    normal_path = None
    emissive_path = None
    mapping_version = None
    animation_names = []
    frame_count = None
    fps = args.fps

    manifest = _read_manifest_raw(manifest_path)
    if manifest is not None:
        mapping_version = manifest.get("mappingVersion")
        animation_names = list(manifest.get("animations", {}).keys())
        frame_count = len(manifest.get("frames", []))
        artifacts.append({"type": "manifest", "path": manifest_path})
        depth_image = manifest.get("depthImage")
        if depth_image:
            depth_path = os.path.join(os.path.dirname(manifest_path), depth_image)
            artifacts.append({"type": "depth_sheet", "path": depth_path})
        normal_image = manifest.get("normalImage")
        if normal_image:
            normal_path = os.path.join(os.path.dirname(manifest_path), normal_image)
            artifacts.append({"type": "normal_sheet", "path": normal_path})
        emissive_image = manifest.get("emissiveImage")
        if emissive_image:
            emissive_path = os.path.join(os.path.dirname(manifest_path), emissive_image)
            artifacts.append({"type": "emissive_sheet", "path": emissive_path})

    world_states = [s.strip() for s in (args.world_states or "").split(",") if s.strip()]
    variants = [v.strip() for v in (args.variants or "").split(",") if v.strip()]

    for name in variants:
        p = base + f"_{name}.png"
        if os.path.isfile(p):
            artifacts.append({"type": "variant_sheet", "path": p})
    for name in world_states:
        p = base + f"_{name}.png"
        if os.path.isfile(p):
            artifacts.append({"type": "world_state_sheet", "path": p})

    return {
        "artifacts": artifacts,
        "manifest_path": manifest_path if manifest is not None else None,
        "sheet_path": sheet_path,
        "depth_path": depth_path,
        "normal_path": normal_path,
        "emissive_path": emissive_path,
        "world_states": world_states,
        "fps": fps,
        "frame_count": frame_count,
        "animation_names": animation_names,
        "mapping_version": mapping_version,
    }


def cmd_render(args, reporter: Reporter):
    from core.renderer import Renderer, RendererConfig, StyleParams

    if not os.path.isfile(args.model):
        raise InputMissingError(f"Model FBX not found: {args.model}")

    # Phase 3: Handle procedural skeleton generation.
    # IMPORTANT: never overwrite the user's input model. Generate the rig to a
    # derived path and render THAT generated rig instead.
    render_model = args.model
    if args.skeleton_generator:
        from core.procedural.skeleton_generator import SkeletonParams, SkeletonGenerator
        reporter.say(f"Generating procedural skeleton (height={args.height_cm}cm, weight={args.weight_kg}kg)...")
        params = SkeletonParams(
            height_cm=args.height_cm,
            weight_kg=args.weight_kg,
            with_ik=args.with_ik,
            with_mesh_bodies=args.mesh_bodies,
        )
        generator = SkeletonGenerator()
        # Resolve a non-destructive output path for the generated rig.
        if getattr(args, "skeleton_output", None):
            skeleton_fbx = args.skeleton_output
        else:
            model_dir = os.path.dirname(os.path.abspath(args.model))
            model_stem = os.path.splitext(os.path.basename(args.model))[0]
            skeleton_fbx = os.path.join(model_dir, f"{model_stem}_procedural.fbx")
        result = generator.generate(params, export_fbx=skeleton_fbx)
        reporter.say(f"  Skeleton: {result['metadata']['total_joints']} joints")
        if result['fbx_path']:
            reporter.say(f"  Rig generated (original model preserved): {result['fbx_path']}")
            render_model = result['fbx_path']

    config = RendererConfig(blender_path=args.blender)
    renderer = Renderer(config)

    ok, version = renderer.check()
    if not ok:
        raise ToolMissingError(f"Blender not available: {version}")
    reporter.say(f"Using: {version}")

    style = StyleParams(
        width=args.width,
        height=args.height,
        fps=args.fps,
        camera_angle=args.camera,
        pixel_size=args.pixel_size,
        enable_depth=args.depth_pass,
        enable_normal=args.normal_pass,
        enable_emissive=args.emissive_pass,
    )

    reporter.say(f"Rendering {render_model} + {args.anim or 'built-in animation'}...")
    if args.depth_pass:
        reporter.say("  (with depth pass enabled)")
    if args.normal_pass:
        reporter.say("  (with normal-map pass enabled)")
    if args.emissive_pass:
        reporter.say("  (with emissive pass enabled)")
    out = renderer.render_and_export(
        char_fbx=render_model,
        anim_fbx=args.anim,
        export_path=args.output,
        export_format=args.format,
        style=style,
        progress_cb=reporter.progress,
        anim_name=args.anim_name,
    )
    reporter.say(f"Done: {out}")

    # Phase 3: Handle palette variants
    if args.variants:
        reporter.say(f"\nGenerating palette variants: {args.variants}")
        from core.procedural.palette_swap import Palette, PaletteSwapper
        from PIL import Image

        variants_list = [v.strip() for v in args.variants.split(",")]

        base_sheet_path = out if out.endswith('.png') else out + '.png'
        if not os.path.exists(base_sheet_path):
            reporter.say(f"  ⚠️ Base sprite sheet not found: {base_sheet_path}")
        else:
            base_sheet = Image.open(base_sheet_path)
            variant_data = {}

            PRESET_PALETTES = {
                'red': Palette.from_hex_map({'#4169E1': '#FF6347', '#6495ED': '#FF4500', '#1E90FF': '#DC143C'}),
                'green': Palette.from_hex_map({'#4169E1': '#228B22', '#6495ED': '#32CD32', '#1E90FF': '#00AA00'}),
                'purple': Palette.from_hex_map({'#4169E1': '#9932CC', '#6495ED': '#DA70D6', '#1E90FF': '#8A2BE2'}),
                'gold': Palette.from_hex_map({'#4169E1': '#FFD700', '#6495ED': '#FFA500', '#1E90FF': '#FF8C00'}),
            }

            for variant_name in variants_list:
                if variant_name not in PRESET_PALETTES:
                    reporter.say(f"  ⚠️ Unknown variant: {variant_name} (skip)")
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
                reporter.say(f"  ✓ {variant_name}: {variant_path}")

            manifest_path = out.replace('.png', '_manifest.json')
            if os.path.exists(manifest_path) and variant_data:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                manifest['variants'] = [{'name': k, 'path': v['path']} for k, v in variant_data.items()]
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f, indent=2)
                reporter.say(f"  ✓ Manifest updated with {len(variant_data)} variants")

    # SHADED world-state hooks: generate REAL per-state actor variants
    if args.world_states:
        reporter.say(f"\nGenerating SHADED world-state variants: {args.world_states}")
        from core.procedural.world_states import apply_world_state, list_world_states
        from core.sprite_sheet import WorldStateRef

        world_states_list = [v.strip() for v in args.world_states.split(",") if v.strip()]
        available = set(list_world_states())

        base_sheet_path = out if out.endswith('.png') else out + '.png'
        if not os.path.exists(base_sheet_path):
            reporter.say(f"  ⚠️ Base sprite sheet not found: {base_sheet_path}")
        else:
            base_sheet = Image.open(base_sheet_path).convert("RGBA")
            ws_manifest = {}

            for entry in world_states_list:
                if "=" in entry:
                    state_name, intensity_str = entry.split("=", 1)
                    state_name = state_name.strip()
                    try:
                        intensity = float(intensity_str.strip())
                    except ValueError:
                        intensity = 0.5
                else:
                    state_name = entry
                    intensity = 0.5
                intensity = max(0.0, min(1.0, intensity))

                if state_name not in available:
                    reporter.say(f"  ⚠️ Unknown world state: {state_name} (skip)")
                    continue

                variant_sheet = apply_world_state(base_sheet, state_name, intensity)
                variant_path = out.replace('.png', f'_{state_name}.png')
                variant_sheet.save(variant_path, 'PNG')
                ws_manifest[state_name] = WorldStateRef(
                    name=state_name,
                    transform=state_name,
                    intensity=intensity,
                    variant_path=os.path.basename(variant_path),
                )
                reporter.say(f"  ✓ {state_name} (intensity={intensity:.2f}): {variant_path}")

            manifest_path = out.replace('.png', '_manifest.json')
            if os.path.exists(manifest_path) and ws_manifest:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                manifest['worldStates'] = {
                    name: ref.to_dict() for name, ref in ws_manifest.items()
                }
                with open(manifest_path, 'w') as f:
                    json.dump(manifest, f, indent=2)
                reporter.say(f"  ✓ Manifest updated with {len(ws_manifest)} world states")

    if reporter.json_mode:
        _emit_success(reporter, "render", **_build_render_summary(args, out))


def cmd_analyze(args, reporter: Reporter):
    from ai.style_analyzer import StyleAnalyzer

    key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise InputMissingError("Set ANTHROPIC_API_KEY or pass --api-key")

    analyzer = StyleAnalyzer(api_key=key)
    style = analyzer.analyze_sheet(args.sheet)
    reporter.say(f"Style parameters extracted from {args.sheet}:")
    reporter.say(f"  Size:         {style.width}x{style.height}px")
    reporter.say(f"  FPS:          {style.fps}")
    reporter.say(f"  Camera:       {style.camera_angle}")
    reporter.say(f"  Pixel size:   {style.pixel_size}")
    reporter.say(f"  Palette hint: {style.palette_hint}")
    reporter.say(f"  Exaggeration: {style.exaggeration}")

    if reporter.json_mode:
        _emit_success(
            reporter,
            "analyze",
            artifacts=[],
            sheet_path=args.sheet,
            style={
                "width": style.width,
                "height": style.height,
                "fps": style.fps,
                "camera_angle": style.camera_angle,
                "pixel_size": style.pixel_size,
                "palette_hint": style.palette_hint,
                "exaggeration": style.exaggeration,
            },
        )


def cmd_mocap(args, reporter: Reporter):
    from core.mocap.video_tracker import VideoTracker
    from core.mocap.bvh_exporter import export_bvh

    if not os.path.isfile(args.video):
        raise InputMissingError(f"Video not found: {args.video}")

    tracker = VideoTracker()
    reporter.say(f"Tracking {args.video}...")

    def progress(frame, total):
        if frame % 30 == 0:
            pct = int(frame / max(total, 1) * 100)
            reporter.progress(f"{pct}% ({frame}/{total} frames)")

    result = tracker.track(args.video, progress_cb=progress)
    if not result.success:
        raise RuntimeError(result.error)

    out = args.output or os.path.splitext(args.video)[0] + ".bvh"
    export_bvh(result, out)
    reporter.say(f"Done: {out} ({result.total_frames} frames at {result.fps:.1f}fps)")

    if reporter.json_mode:
        _emit_success(
            reporter,
            "mocap",
            artifacts=[{"type": "bvh", "path": out}],
            sheet_path=None,
            manifest_path=None,
            frame_count=result.total_frames,
            fps=round(result.fps, 2),
        )


def cmd_video2sprite(args, reporter: Reporter):
    from core.video_to_sprite.frame_extractor import extract_frames
    from core.video_to_sprite.pixelizer import pixelize_sequence, PixelizeConfig
    from core.exporter import Exporter
    import tempfile

    if not os.path.isfile(args.video):
        raise InputMissingError(f"Video not found: {args.video}")

    frames_dir = tempfile.mkdtemp(prefix="swift_v2s_")
    reporter.say(f"Extracting frames from {args.video}...")
    result = extract_frames(
        args.video, frames_dir,
        keyframes_only=args.keyframes,
    )
    if not result.success:
        raise RuntimeError(result.error)
    reporter.say(f"  {len(result.frames)} frames extracted")

    pixel_dir = tempfile.mkdtemp(prefix="swift_px_")
    cfg = PixelizeConfig(
        target_width=args.width,
        target_height=args.height,
        palette_colors=args.colors,
        lock_palette=True,
    )
    reporter.say("Pixelizing...")
    pixel_frames = pixelize_sequence([f.path for f in result.frames], pixel_dir, cfg)

    out = args.output or os.path.splitext(args.video)[0] + "_sprites.png"
    exporter = Exporter(pixel_frames, fps=int(result.fps))
    if args.format == "gif":
        out = os.path.splitext(out)[0] + ".gif"
        exporter.to_gif(out)
    elif args.format == "frames":
        out = os.path.splitext(out)[0] + "_frames"
        exporter.to_frames_json(out)
    else:
        exporter.to_sprite_sheet(out)
    reporter.say(f"Done: {out}")

    if reporter.json_mode:
        _emit_success(
            reporter,
            "video2sprite",
            artifacts=[{"type": args.format, "path": out}],
            sheet_path=out,
            manifest_path=None,
            fps=int(result.fps),
            frame_count=len(result.frames),
        )


def cmd_spritesheet(args, reporter: Reporter):
    from core.sprite_sheet import SpriteSheetManifest, SpriteSheet

    if not os.path.isfile(args.image):
        raise InputMissingError(f"Sprite sheet image not found: {args.image}")
    if not os.path.isfile(args.manifest):
        raise InputMissingError(f"Manifest not found: {args.manifest}")

    manifest = SpriteSheetManifest.from_file(args.manifest)
    sheet = SpriteSheet(args.image, manifest)
    manifest_raw = _read_manifest_raw(args.manifest) or {}

    if args.action == "list":
        reporter.say("Animations:")
        for name in sheet.list_animations():
            anim = manifest.animations[name]
            reporter.say(f"  {name:20s}  {len(anim.frames)} frames  {anim.fps}fps  {'loop' if anim.loop else 'once'}")
        reporter.say(f"\nFrames: {len(sheet.list_frame_ids())}")

        if reporter.json_mode:
            _emit_success(
                reporter,
                "spritesheet",
                action="list",
                artifacts=[],
                sheet_path=args.image,
                manifest_path=args.manifest,
                mapping_version=manifest_raw.get("mappingVersion"),
                animation_names=sheet.list_animations(),
                frame_count=len(sheet.list_frame_ids()),
                fps=(next(iter(manifest.animations.values())).fps if manifest.animations else None),
            )

    elif args.action == "export":
        if not args.anim:
            raise InputMissingError("Missing required --anim for export")
        out = args.output or f"{args.anim}.{args.format}"
        if args.format == "gif":
            result = sheet.export_animation_gif(args.anim, out)
        else:
            result = sheet.export_animation_sheet(args.anim, out)
        reporter.say(f"Done: {result}")

        if reporter.json_mode:
            _emit_success(
                reporter,
                "spritesheet",
                action="export",
                artifacts=[{"type": args.format, "path": result}],
                sheet_path=args.image,
                manifest_path=args.manifest,
                mapping_version=manifest_raw.get("mappingVersion"),
                animation_names=[args.anim],
                frame_count=len(manifest.animations[args.anim].frames),
                fps=manifest.animations[args.anim].fps,
            )

    elif args.action == "extract":
        if not args.frame:
            raise InputMissingError("Missing required --frame for extract")
        img = sheet.extract_frame(args.frame)
        out = args.output or f"{args.frame}.png"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        img.save(out)
        reporter.say(f"Done: {out} ({img.size[0]}×{img.size[1]})")

        if reporter.json_mode:
            _emit_success(
                reporter,
                "spritesheet",
                action="extract",
                artifacts=[{"type": "frame", "path": out}],
                sheet_path=args.image,
                manifest_path=args.manifest,
                mapping_version=manifest_raw.get("mappingVersion"),
                frame_id=args.frame,
                frame_size=[img.size[0], img.size[1]],
            )


def cmd_gui(args, reporter: Reporter):
    try:
        from gui.app import main as gui_main
    except ImportError as exc:
        raise ToolMissingError(f"GUI requires PySide6 ({exc})")
    gui_main()


def build_parser():
    parser = argparse.ArgumentParser(prog="swift", description="SWIFT Sprite Animation AI Workflow")

    # Shared parent: machine-readable JSON summary flag (SWIFT <-> ANVIL contract)
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json", "--json-summary",
        dest="json",
        action="store_true",
        help="Emit a single machine-readable JSON summary to STDOUT on success "
             "(all progress/diagnostics go to STDERR). On failure, a "
             '{"status":"error","error":<msg>} object is written to STDERR and '
             "the process exits non-zero.",
    )

    sub = parser.add_subparsers(dest="command")

    # gui
    sub.add_parser("gui", parents=[json_parent], help="Launch the PySide6 GUI")

    # render
    p_render = sub.add_parser("render", parents=[json_parent], help="Render FBX character + animation to sprite sheet")
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
    p_render.add_argument("--skeleton-output", help="Output FBX path for the generated rig (default: <model>_procedural.fbx, never overwrites input)")
    # Phase 3: Depth rendering
    p_render.add_argument("--depth-pass", action="store_true", help="Enable Z-buffer depth pass (8-bit grayscale)")
    # Phase 3: Multi-pass rendering (normal + emissive)
    p_render.add_argument("--normal-pass", action="store_true", help="Enable normal-map pass (RGB PNG)")
    p_render.add_argument("--emissive-pass", action="store_true", help="Enable emissive pass (emission-only RGB PNG)")
    # Phase 3: Palette variants
    p_render.add_argument("--variants", help="Comma-separated palette variant names (e.g. 'red,blue,green')")
    # SHADED world-state hooks
    p_render.add_argument("--world-states", help="Comma-separated SHADED world states (e.g. 'dust,aging,heat')")

    # analyze
    p_analyze = sub.add_parser("analyze", parents=[json_parent], help="Extract style params from a reference sheet")
    p_analyze.add_argument("sheet", help="Path to reference sheet image")
    p_analyze.add_argument("--api-key", help="Anthropic API key")

    # mocap
    p_mocap = sub.add_parser("mocap", parents=[json_parent], help="Video motion capture → BVH")
    p_mocap.add_argument("video", help="Input video file")
    p_mocap.add_argument("--output", help="Output BVH path")

    # video2sprite
    p_v2s = sub.add_parser("video2sprite", parents=[json_parent], help="Convert video frames to pixel art sprite sheet")
    p_v2s.add_argument("video", help="Input video file")
    p_v2s.add_argument("--output", help="Output path")
    p_v2s.add_argument("--format", choices=["sprite_sheet", "gif", "frames"], default="sprite_sheet")
    p_v2s.add_argument("--width", type=int, default=64)
    p_v2s.add_argument("--height", type=int, default=64)
    p_v2s.add_argument("--colors", type=int, default=16)
    p_v2s.add_argument("--keyframes", action="store_true", help="Extract keyframes only")

    # spritesheet
    p_ss = sub.add_parser("spritesheet", parents=[json_parent], help="Work with sprite sheets + manifest")
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
        sys.exit(EXIT_OK)

    reporter = Reporter(json_mode=getattr(args, "json", False))

    dispatch = {
        "render": cmd_render,
        "analyze": cmd_analyze,
        "mocap": cmd_mocap,
        "video2sprite": cmd_video2sprite,
        "spritesheet": cmd_spritesheet,
        "gui": cmd_gui,
    }

    try:
        dispatch[args.command](args, reporter)
    except InputMissingError as exc:
        _emit_error(reporter, str(exc), EXIT_MISSING_INPUT)
    except ToolMissingError as exc:
        _emit_error(reporter, str(exc), EXIT_TOOL_MISSING)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level safety net for ANVIL
        _emit_error(reporter, str(exc), EXIT_GENERIC)


if __name__ == "__main__":
    main()
