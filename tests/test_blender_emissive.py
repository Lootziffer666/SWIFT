"""
Blender-side node-graph unit tests for the emissive pass.

These exercise the pure node-graph builder (build_emissive_compositor) against a
dependency-free fake node tree (make_fake_node_tree), so they run WITHOUT a
Blender install. Tests that genuinely require `bpy` (e.g. material override) are
guarded/skipped.
"""
import os
import pytest

from scripts.blender_render import (
    build_emissive_compositor,
    make_fake_node_tree,
    BLENDER,
)

requires_bpy = pytest.mark.skipif(not BLENDER, reason="needs Blender (bpy)")


class TestEmissiveNodeGraph:
    def test_builds_expected_node_types(self):
        tree = make_fake_node_tree()
        build_emissive_compositor(tree, "/tmp/emissive", "frame_####_emissive.png")
        types = {n.type for n in tree.nodes}
        assert "CompositorNodeRLayers" in types
        assert "CompositorNodeFile" in types

    def test_file_output_targets_emissive_dir(self):
        tree = make_fake_node_tree()
        out_dir = "/out/emissive"
        build_emissive_compositor(tree, out_dir, "frame_####_emissive.png")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        assert file_out.base_path == out_dir
        assert file_out.file_slots[0].path == "frame_####_emissive.png"

    def test_file_output_is_rgb_png_8bit(self):
        tree = make_fake_node_tree()
        build_emissive_compositor(tree, "/tmp/emissive")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        assert file_out.format.file_format == "PNG"
        assert file_out.format.color_mode == "RGB"
        assert file_out.format.color_depth == "8"

    def test_links_renderlayer_image_to_fileoutput(self):
        tree = make_fake_node_tree()
        build_emissive_compositor(tree, "/tmp/emissive")
        file_out = next(n for n in tree.nodes if n.type == "CompositorNodeFile")
        rl = next(n for n in tree.nodes if n.type == "CompositorNodeRLayers")
        assert len(tree.links.links) == 1
        frm, to = tree.links.links[0]
        assert frm.node is rl and frm.name == "Image"
        assert to.node is file_out and to.name == 0


class TestEmissiveRenderJobFields:
    def test_render_job_has_enable_emissive(self):
        from core.blender_bridge import RenderJob
        job = RenderJob(char_fbx="c.fbx")
        assert hasattr(job, "enable_emissive")
        assert job.enable_emissive is False

    def test_render_job_enable_emissive_can_be_set(self):
        from core.blender_bridge import RenderJob
        job = RenderJob(char_fbx="c.fbx", enable_emissive=True)
        assert job.enable_emissive is True

    def test_render_result_has_emissive_frames(self):
        from core.blender_bridge import RenderResult
        result = RenderResult(success=True, frames_dir="/t", frame_count=0)
        assert hasattr(result, "emissive_frame_paths")
        assert result.emissive_frame_paths == []


class TestEmissiveRenderResultMethods:
    def test_emissive_frames_only_returns_png(self):
        from core.blender_bridge import RenderResult
        paths = [
            "/t/frame_0001_emissive.png",
            "/t/frame_0002_emissive.exr",
            "/t/frame_0003_emissive.png",
        ]
        result = RenderResult(success=True, frames_dir="/t", frame_count=3, emissive_frame_paths=paths)
        png = result.emissive_frames()
        assert len(png) == 2
        assert all(p.endswith(".png") for p in png)

    def test_emissive_frames_sorted(self):
        from core.blender_bridge import RenderResult
        paths = ["/t/frame_0002_emissive.png", "/t/frame_0001_emissive.png"]
        result = RenderResult(success=True, frames_dir="/t", frame_count=2, emissive_frame_paths=paths)
        assert result.emissive_frames()[0].endswith("0001_emissive.png")


@requires_bpy
def test_build_emissive_on_real_scene():
    import bpy
    bpy.context.scene.use_nodes = True
    tree, file_out = build_emissive_compositor(bpy.context.scene.node_tree, "/tmp/emissive")
    assert file_out.base_path == "/tmp/emissive"
