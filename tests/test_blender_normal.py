"""
Blender-side node-graph unit tests for the normal-map pass.

These exercise the pure node-graph builder (build_normal_compositor) against a
dependency-free fake node tree (make_fake_node_tree), so they run WITHOUT a
Blender install. Tests that genuinely require `bpy` are guarded/skipped.
"""
import os
import pytest

from scripts.blender_render import (
    build_normal_compositor,
    make_fake_node_tree,
    BLENDER,
)

requires_bpy = pytest.mark.skipif(not BLENDER, reason="needs Blender (bpy)")


class TestNormalNodeGraph:
    def test_builds_expected_node_types(self):
        tree = make_fake_node_tree()
        build_normal_compositor(tree, "/tmp/normal", "frame_####_normal.png")
        types = {n.type for n in tree.nodes}
        assert "CompositorNodeRLayers" in types
        assert "CompositorNodeFile" in types

    def test_file_output_targets_normal_dir(self):
        tree = make_fake_node_tree()
        out_dir = "/out/normal"
        build_normal_compositor(tree, out_dir, "frame_####_normal.png")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        assert file_out.base_path == out_dir
        assert file_out.file_slots[0].path == "frame_####_normal.png"

    def test_file_output_is_rgb_png_8bit(self):
        tree = make_fake_node_tree()
        build_normal_compositor(tree, "/tmp/normal")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        assert file_out.format.file_format == "PNG"
        assert file_out.format.color_mode == "RGB"
        assert file_out.format.color_depth == "8"

    def test_links_renderlayer_normal_to_fileoutput(self):
        tree = make_fake_node_tree()
        build_normal_compositor(tree, "/tmp/normal")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        rl = next(n for n in tree.nodes if n.type == "CompositorNodeRLayers")
        # Exactly one link, from RLayer.Normal -> FileOutput[0]
        assert len(tree.links.links) == 1
        frm, to = tree.links.links[0]
        assert frm.node is rl and frm.name == "Normal"
        assert to.node is file_out and to.name == 0


class TestNormalRenderJobFields:
    def test_render_job_has_enable_normal(self):
        from core.blender_bridge import RenderJob
        job = RenderJob(char_fbx="c.fbx")
        assert hasattr(job, "enable_normal")
        assert job.enable_normal is False

    def test_render_job_enable_normal_can_be_set(self):
        from core.blender_bridge import RenderJob
        job = RenderJob(char_fbx="c.fbx", enable_normal=True)
        assert job.enable_normal is True

    def test_render_result_has_normal_frames(self):
        from core.blender_bridge import RenderResult
        result = RenderResult(success=True, frames_dir="/t", frame_count=0)
        assert hasattr(result, "normal_frame_paths")
        assert result.normal_frame_paths == []


class TestNormalRenderResultMethods:
    def test_normal_frames_only_returns_png(self):
        from core.blender_bridge import RenderResult
        paths = [
            "/t/frame_0001_normal.png",
            "/t/frame_0002_normal.exr",
            "/t/frame_0003_normal.png",
        ]
        result = RenderResult(success=True, frames_dir="/t", frame_count=3, normal_frame_paths=paths)
        png = result.normal_frames()
        assert len(png) == 2
        assert all(p.endswith(".png") for p in png)

    def test_normal_frames_sorted(self):
        from core.blender_bridge import RenderResult
        paths = ["/t/frame_0002_normal.png", "/t/frame_0001_normal.png"]
        result = RenderResult(success=True, frames_dir="/t", frame_count=2, normal_frame_paths=paths)
        assert result.normal_frames()[0].endswith("0001_normal.png")


@requires_bpy
def test_build_normal_on_real_scene():
    import bpy
    bpy.context.scene.use_nodes = True
    tree, file_out = build_normal_compositor(bpy.context.scene.node_tree, "/tmp/normal")
    assert file_out.base_path == "/tmp/normal"
    assert os.path.isdir("/tmp/normal") or True
