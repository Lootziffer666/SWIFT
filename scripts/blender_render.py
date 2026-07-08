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
import tempfile

try:
    import bpy
    import mathutils
    BLENDER = True
except ImportError:
    BLENDER = False


# ── Fake Blender compositor node-tree stub ───────────────────────────────────
# A tiny, dependency-free stand-in for a Blender scene.node_tree. Lets the pure
# node-graph builders below be unit-tested WITHOUT `bpy` installed. Exposed via
# make_fake_node_tree() so tests can assert node types/links.
class _FakeSocket:
    def __init__(self, node, name):
        self.node = node
        self.name = name
        self.default_value = None


class _FakeIONode:
    def __init__(self, node):
        self._node = node
        self._sockets = {}

    def _get(self, key):
        if key not in self._sockets:
            self._sockets[key] = _FakeSocket(self._node, key)
        return self._sockets[key]

    def __getitem__(self, key):
        if isinstance(key, int):
            items = list(self._sockets.values())
            while len(items) <= key:
                self._get(len(items))
                items = list(self._sockets.values())
            return items[key]
        return self._get(key)

    def __setitem__(self, key, value):
        self._get(key).default_value = value

    def __iter__(self):
        return iter(self._sockets.values())


class _FakeFileSlot:
    def __init__(self):
        self.path = ""


class _FakeFormat:
    def __init__(self):
        self.file_format = ""
        self.color_mode = ""
        self.color_depth = ""


class _FakeNode:
    def __init__(self, node_type):
        self.type = node_type
        self.name = None
        self.inputs = _FakeIONode(self)
        self.outputs = _FakeIONode(self)
        self.operation = None
        self.base_path = ""
        self.file_slots = [_FakeFileSlot()]
        self.format = _FakeFormat()


class _FakeNodes:
    def __init__(self):
        self._list = []

    def new(self, type):
        node = _FakeNode(type)
        node.name = f"{type}_{len(self._list)}"
        self._list.append(node)
        return node

    def remove(self, node):
        if node in self._list:
            self._list.remove(node)

    def __iter__(self):
        return iter(self._list)

    def __len__(self):
        return len(self._list)


class _FakeLinks:
    def __init__(self):
        self.links = []

    def new(self, frm, to):
        self.links.append((frm, to))
        return (frm, to)


class _FakeNodeTree:
    def __init__(self):
        self.nodes = _FakeNodes()
        self.links = _FakeLinks()


def make_fake_node_tree():
    """Return a minimal fake Blender compositor node tree for unit tests."""
    return _FakeNodeTree()


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
    parser.add_argument("--depth-pass", action="store_true",
                        help="Enable Z-buffer depth pass (outputs grayscale PNG)")
    parser.add_argument("--normal-pass", action="store_true",
                        help="Enable normal-map pass (outputs RGB PNG)")
    parser.add_argument("--emissive-pass", action="store_true",
                        help="Enable emissive pass (outputs emission-only RGB PNG)")
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


# ── Pure node-graph builders (testable WITHOUT bpy) ─────────────────────────
# Each builder takes a compositor node tree (real `scene.node_tree` or the fake
# one from make_fake_node_tree) plus an output directory and a per-frame filename
# pattern. It clears the tree, wires up the appropriate pass, and returns the
# (tree, file_output_node). The File Output node writes to `<out_dir>/<filename>`
# with `####` expanded to the scene frame number by Blender's animation render.

DEPTH_SUFFIX = "depth"
NORMAL_SUFFIX = "normal"
EMISSIVE_SUFFIX = "emissive"


def build_depth_compositor(tree, out_dir, filename=f"frame_####_{DEPTH_SUFFIX}.png"):
    """Build a Z-depth → 8-bit grayscale PNG pass (0-255)."""
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new(type="CompositorNodeRLayers")

    # Normalize Z to 0-1 (objects assumed within 0.1..100 units of camera)
    map_range = tree.nodes.new(type="CompositorNodeMapRange")
    map_range.inputs["From Min"].default_value = 0.1
    map_range.inputs["From Max"].default_value = 100.0
    tree.links.new(render_layers.outputs["Z"], map_range.inputs["Value"])

    # Scale to 0-255 (8-bit grayscale)
    math_mult = tree.nodes.new(type="CompositorNodeMath")
    math_mult.operation = "MULTIPLY"
    math_mult.inputs[1].default_value = 255.0
    tree.links.new(map_range.outputs["Result"], math_mult.inputs[0])

    file_output = tree.nodes.new(type="CompositorNodeFile")
    file_output.base_path = out_dir
    file_output.format.file_format = "PNG"
    file_output.format.color_mode = "BW"
    file_output.format.color_depth = "8"
    file_output.file_slots[0].path = filename
    tree.links.new(math_mult.outputs[0], file_output.inputs[0])

    return tree, file_output


def build_normal_compositor(tree, out_dir, filename=f"frame_####_{NORMAL_SUFFIX}.png"):
    """Build a tangent-space Normal pass → RGB PNG."""
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new(type="CompositorNodeRLayers")

    file_output = tree.nodes.new(type="CompositorNodeFile")
    file_output.base_path = out_dir
    file_output.format.file_format = "PNG"
    file_output.format.color_mode = "RGB"
    file_output.format.color_depth = "8"
    file_output.file_slots[0].path = filename
    tree.links.new(render_layers.outputs["Normal"], file_output.inputs[0])

    return tree, file_output


def build_emissive_compositor(tree, out_dir, filename=f"frame_####_{EMISSIVE_SUFFIX}.png"):
    """Build an emission-only pass → RGB PNG.

    The render output itself is taken from the standard Image output; callers
    must first override materials with emission-only copies (see
    _apply_emissive_override) so the rendered image IS the emissive map.
    """
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new(type="CompositorNodeRLayers")

    file_output = tree.nodes.new(type="CompositorNodeFile")
    file_output.base_path = out_dir
    file_output.format.file_format = "PNG"
    file_output.format.color_mode = "RGB"
    file_output.format.color_depth = "8"
    file_output.file_slots[0].path = filename
    tree.links.new(render_layers.outputs["Image"], file_output.inputs[0])

    return tree, file_output


# ── Emissive material override (Blender-only) ───────────────────────────────

def _extract_base_color(mat):
    """Best-effort extraction of a material's diffuse/base color."""
    if getattr(mat, "use_nodes", False):
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                val = node.inputs["Base Color"].default_value
                return tuple(val)
    return tuple(getattr(mat, "diffuse_color", (1.0, 1.0, 1.0, 1.0)))


def _apply_emissive_override(scene):
    """Replace every mesh material with an emission-only copy of its base color."""
    if not BLENDER:
        return
    scene.swift_original_materials = []
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            orig = slot.material
            if orig is None:
                continue
            scene.swift_original_materials.append((slot, orig))
            new_mat = bpy.data.materials.new(name=f"SWIFT_EMISSIVE_{orig.name}")
            new_mat.use_nodes = True
            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links
            for n in list(nodes):
                nodes.remove(n)
            out_node = nodes.new(type="ShaderNodeOutputMaterial")
            emit_node = nodes.new(type="ShaderNodeEmission")
            emit_node.inputs["Color"].default_value = _extract_base_color(orig)
            links.new(emit_node.outputs["Emission"], out_node.inputs["Surface"])
            slot.material = new_mat


def _restore_materials(scene):
    """Restore original materials and dispose the temporary emissive copies."""
    if not BLENDER:
        return
    for slot, orig in getattr(scene, "swift_original_materials", []):
        slot.material = orig
    scene.swift_original_materials = []
    for mat in list(bpy.data.materials):
        if mat.name.startswith("SWIFT_EMISSIVE_"):
            bpy.data.materials.remove(mat)


def configure_render(scene, out_dir, width, height, fps):
    """Configure the color (RGBA) render output to <out_dir>/frame_*.png."""
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.fps = fps

    # Color RGBA render (transparent background)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True

    scene.render.filepath = os.path.join(out_dir, "frame_")
    os.makedirs(out_dir, exist_ok=True)


def render_frames(scene, start, end):
    scene.frame_start = start
    scene.frame_end = end
    bpy.ops.render.render(animation=True)


def _render_pass_frames(
    scene,
    out_dir,
    start,
    end,
    build_fn,
    filename,
    prepare=None,
    cleanup=None,
):
    """Render a single multi-pass output via the compositor File Output node.

    The color render is redirected to a throwaway temp path so it does not
    pollute <out_dir>; only the File Output node in `build_fn` writes the actual
    pass frames into <out_dir>/<filename> (with `####` → frame number).
    """
    original_filepath = scene.render.filepath
    original_use_nodes = scene.use_nodes

    if prepare:
        prepare(scene)
    scene.use_nodes = True
    build_fn(scene.node_tree, out_dir, filename)

    tmp_dir = tempfile.mkdtemp(prefix="swift_pass_")
    scene.render.filepath = os.path.join(tmp_dir, "frame_")
    scene.frame_start = start
    scene.frame_end = end
    try:
        bpy.ops.render.render(animation=True)
    finally:
        scene.use_nodes = original_use_nodes
        scene.render.filepath = original_filepath
        if cleanup:
            cleanup(scene)

    print(f"SWIFT: Rendered pass frames to {out_dir}")


def render_depth_frames(scene, out_dir, start, end, width=None, height=None):
    """Render depth pass (8-bit grayscale PNGs) into <out_dir>."""
    _render_pass_frames(
        scene, out_dir, start, end,
        build_depth_compositor, f"frame_####_{DEPTH_SUFFIX}.png",
    )


def render_normal_frames(scene, out_dir, start, end, width=None, height=None):
    """Render normal pass (RGB PNGs) into <out_dir>."""
    _render_pass_frames(
        scene, out_dir, start, end,
        build_normal_compositor, f"frame_####_{NORMAL_SUFFIX}.png",
    )


def render_emissive_frames(scene, out_dir, start, end, width=None, height=None):
    """Render emissive pass (RGB PNGs) into <out_dir>."""
    _render_pass_frames(
        scene, out_dir, start, end,
        build_emissive_compositor, f"frame_####_{EMISSIVE_SUFFIX}.png",
        prepare=_apply_emissive_override,
        cleanup=_restore_materials,
    )


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

    # Always render the color frames first.
    render_frames(scene, start, end)
    write_metadata(args.out, args, end - start + 1)
    print(f"SWIFT: Rendered {end - start + 1} frames to {args.out}")

    # Optional multi-pass outputs (each into its own subdir).
    if args.depth_pass:
        depth_out = os.path.join(args.out, "depth")
        os.makedirs(depth_out, exist_ok=True)
        render_depth_frames(scene, depth_out, start, end, args.width, args.height)
        print(f"SWIFT: Rendered {end - start + 1} depth frames to {depth_out}")

    if args.normal_pass:
        normal_out = os.path.join(args.out, "normal")
        os.makedirs(normal_out, exist_ok=True)
        render_normal_frames(scene, normal_out, start, end, args.width, args.height)
        print(f"SWIFT: Rendered {end - start + 1} normal frames to {normal_out}")

    if args.emissive_pass:
        emissive_out = os.path.join(args.out, "emissive")
        os.makedirs(emissive_out, exist_ok=True)
        render_emissive_frames(scene, emissive_out, start, end, args.width, args.height)
        print(f"SWIFT: Rendered {end - start + 1} emissive frames to {emissive_out}")


if __name__ == "__main__":
    main()
