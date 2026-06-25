"""
Blender-internal render script. Run via:
  blender --background --python scripts/blender_render.py -- \
    --fbx path/to/char.fbx --anim path/to/walk.fbx \
    --out /tmp/frames/ --width 64 --height 64 --fps 12
"""
import sys
import os
import json
import argparse

try:
    import bpy
    import mathutils
    BLENDER = True
except ImportError:
    BLENDER = False


def parse_args():
    # Blender passes its own args before '--'; everything after is ours
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="SWIFT Blender render script")
    parser.add_argument("--fbx", required=True, help="Path to character FBX")
    parser.add_argument("--anim", default=None, help="Path to animation FBX (optional if char has actions)")
    parser.add_argument("--out", required=True, help="Output directory for PNG frames")
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--camera-angle", choices=["front", "side", "three-quarter"], default="front")
    parser.add_argument("--pixel-size", type=int, default=4, help="Pixel art block size for post-process")
    parser.add_argument("--meta", default=None, help="Output path for metadata JSON")
    parser.add_argument("--lock-root-motion", action="store_true",
                        help="Lock root bone XZ position (use with _RM animations)")
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path):
    bpy.ops.import_scene.fbx(filepath=path)
    return [obj for obj in bpy.context.selected_objects]


def setup_orthographic_camera(angle="front"):
    cam_data = bpy.data.cameras.new("SWIFT_Camera")
    cam_data.type = "ORTHO"
    cam_obj = bpy.data.objects.new("SWIFT_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    positions = {
        "front":         (0, -5, 0.9),
        "side":          (5,  0, 0.9),
        "three-quarter": (3.5, -3.5, 0.9),
    }
    rotations = {
        "front":         (90, 0, 0),
        "side":          (90, 0, 90),
        "three-quarter": (90, 0, 45),
    }
    import math
    pos = positions.get(angle, positions["front"])
    rot = rotations.get(angle, rotations["front"])
    cam_obj.location = pos
    cam_obj.rotation_euler = [math.radians(r) for r in rot]

    # Auto-fit orthographic scale to scene bounds
    all_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if all_objs:
        max_dim = max(max(o.dimensions) for o in all_objs)
        cam_data.ortho_scale = max(max_dim * 1.2, 1.5)
    else:
        cam_data.ortho_scale = 2.0

    return cam_obj


def setup_flat_lighting():
    # Remove existing lights
    for obj in list(bpy.context.scene.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)

    # Single flat directional light
    light_data = bpy.data.lights.new("SWIFT_Light", type="SUN")
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new("SWIFT_Light", light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = (2, -2, 4)


def lock_root_bone(char_objects):
    """Lock root bone XZ to keep character centered during _RM animation render."""
    if not BLENDER:
        return
    root_names = {"root", "root_motion", "hips", "pelvis"}
    for obj in char_objects:
        if obj.type != "ARMATURE":
            continue
        for bone in obj.data.bones:
            if bone.name.lower() in root_names:
                pose_bone = obj.pose.bones.get(bone.name)
                if pose_bone:
                    c = pose_bone.constraints.new("LIMIT_LOCATION")
                    c.use_min_x = c.use_max_x = True
                    c.use_min_z = c.use_max_z = True
                break


def apply_animation(char_objects, anim_path):
    """Import anim FBX and retarget to existing armature if possible."""
    if not anim_path or not os.path.exists(anim_path):
        return

    armature = next((o for o in char_objects if o.type == "ARMATURE"), None)
    if not armature:
        return

    # Import animation FBX – actions will appear in bpy.data.actions
    before = set(bpy.data.actions.keys())
    bpy.ops.import_scene.fbx(filepath=anim_path, use_anim=True)
    after = set(bpy.data.actions.keys())
    new_actions = after - before

    if new_actions:
        action_name = list(new_actions)[0]
        action = bpy.data.actions[action_name]
        if armature.animation_data is None:
            armature.animation_data_create()
        armature.animation_data.action = action


def configure_render(scene, out_dir, width, height, fps):
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.fps = fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.filepath = os.path.join(out_dir, "frame_")
    os.makedirs(out_dir, exist_ok=True)


def render_frames(scene, start, end):
    scene.frame_start = start
    scene.frame_end = end
    bpy.ops.render.render(animation=True)


def write_metadata(out_dir, args, frame_count):
    meta = {
        "frame_count": frame_count,
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "frames_dir": out_dir,
        "frame_prefix": "frame_",
    }
    meta_path = args.meta or os.path.join(out_dir, "meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    return meta_path


def main():
    if not BLENDER:
        print("ERROR: This script must run inside Blender.")
        sys.exit(1)

    args = parse_args()
    os.makedirs(args.out, exist_ok=True)

    clear_scene()
    scene = bpy.context.scene

    char_objects = import_fbx(args.fbx)
    apply_animation(char_objects, args.anim)
    if args.lock_root_motion:
        lock_root_bone(char_objects)

    setup_flat_lighting()
    setup_orthographic_camera(args.camera_angle)

    # Determine frame range
    start = args.start
    if args.end is not None:
        end = args.end
    else:
        # Use scene frame range set by imported animation
        end = scene.frame_end if scene.frame_end > start else start + 11

    configure_render(scene, args.out, args.width, args.height, args.fps)
    render_frames(scene, start, end)
    write_metadata(args.out, args, end - start + 1)
    print(f"SWIFT: Rendered {end - start + 1} frames to {args.out}")


if __name__ == "__main__":
    main()
