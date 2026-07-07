"""
Tests for core/blender_bridge.py depth rendering functionality.
"""
import pytest
import tempfile
import os
from core.blender_bridge import RenderJob, RenderResult


class TestDepthRenderingFields:
    def test_render_job_depth_flag(self):
        """RenderJob should have enable_depth flag."""
        job = RenderJob(char_fbx="char.fbx")
        assert hasattr(job, "enable_depth")
        assert job.enable_depth is False

    def test_render_job_depth_flag_enabled(self):
        """RenderJob depth flag can be enabled."""
        job = RenderJob(char_fbx="char.fbx", enable_depth=True)
        assert job.enable_depth is True

    def test_render_result_depth_frames(self):
        """RenderResult should have depth_frame_paths field."""
        result = RenderResult(success=True, frames_dir="/tmp", frame_count=0)
        assert hasattr(result, "depth_frame_paths")
        assert result.depth_frame_paths == []

    def test_render_result_with_depth_frames(self):
        """RenderResult can store depth frame paths."""
        depth_frames = ["/tmp/frame_0001_depth.png", "/tmp/frame_0002_depth.png"]
        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=2,
            depth_frame_paths=depth_frames,
        )
        assert result.depth_frame_paths == depth_frames

    def test_depth_frames_method(self):
        """RenderResult.depth_frames() returns sorted depth PNG paths."""
        depth_frames = ["/tmp/frame_0002_depth.png", "/tmp/frame_0001_depth.png"]
        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=2,
            depth_frame_paths=depth_frames,
        )
        sorted_frames = result.depth_frames()
        assert len(sorted_frames) == 2
        assert sorted_frames[0].endswith("0001_depth.png")
        assert sorted_frames[1].endswith("0002_depth.png")


class TestDepthFrameValidation:
    def test_depth_and_color_frames_independent(self):
        """Depth frames should be tracked independently of color frames."""
        color_frames = ["/tmp/frame_0001.png", "/tmp/frame_0002.png"]
        depth_frames = ["/tmp/frame_0001_depth.png", "/tmp/frame_0002_depth.png"]

        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=2,
            frame_paths=color_frames,
            depth_frame_paths=depth_frames,
        )

        assert len(result.sprite_frames()) == 2
        assert len(result.depth_frames()) == 2
        assert result.sprite_frames()[0].endswith("0001.png")
        assert result.depth_frames()[0].endswith("0001_depth.png")

    def test_depth_frames_only_returns_png(self):
        """depth_frames() should filter to PNG only."""
        depth_frames = [
            "/tmp/frame_0001_depth.png",
            "/tmp/frame_0002_depth.exr",  # Non-PNG
            "/tmp/frame_0003_depth.png",
        ]
        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=3,
            depth_frame_paths=depth_frames,
        )
        png_only = result.depth_frames()
        assert len(png_only) == 2
        assert all(p.endswith(".png") for p in png_only)

    def test_empty_depth_frames(self):
        """Empty depth_frame_paths should be handled gracefully."""
        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=0,
            depth_frame_paths=[],
        )
        assert result.depth_frames() == []
        assert len(result.depth_frames()) == 0


class TestDepthRenderConfiguration:
    def test_render_job_preserves_all_params_with_depth(self):
        """Adding depth flag shouldn't lose other parameters."""
        job = RenderJob(
            char_fbx="char.fbx",
            anim_fbx="anim.fbx",
            width=128,
            height=128,
            fps=24,
            enable_depth=True,
        )
        assert job.char_fbx == "char.fbx"
        assert job.anim_fbx == "anim.fbx"
        assert job.width == 128
        assert job.height == 128
        assert job.fps == 24
        assert job.enable_depth is True

    def test_render_result_success_independent_of_depth(self):
        """Success flag should be independent of depth frame presence."""
        result_with_depth = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=2,
            frame_paths=["/tmp/frame_0001.png"],
            depth_frame_paths=["/tmp/frame_0001_depth.png"],
        )
        assert result_with_depth.success is True

        result_no_depth = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=1,
            frame_paths=["/tmp/frame_0001.png"],
            depth_frame_paths=[],
        )
        assert result_no_depth.success is True

    def test_render_result_error_with_depth_data(self):
        """Error results can still carry partial depth data."""
        result = RenderResult(
            success=False,
            frames_dir="/tmp",
            frame_count=0,
            depth_frame_paths=[],
            error="Render failed",
        )
        assert result.success is False
        assert result.error is not None


class TestDepthFrameMetadata:
    def test_depth_frames_match_color_frame_count(self):
        """For successful depth renders, frame counts should match."""
        color_count = 12
        color_frames = [f"/tmp/frame_{i:04d}.png" for i in range(1, color_count + 1)]
        depth_frames = [f"/tmp/frame_{i:04d}_depth.png" for i in range(1, color_count + 1)]

        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=color_count,
            frame_paths=color_frames,
            depth_frame_paths=depth_frames,
        )

        assert len(result.sprite_frames()) == len(result.depth_frames())

    def test_depth_frames_naming_convention(self):
        """Depth frames should follow frame_XXXX_depth.png naming."""
        depth_frames = [
            "/tmp/frame_0001_depth.png",
            "/tmp/frame_0002_depth.png",
        ]
        result = RenderResult(
            success=True,
            frames_dir="/tmp",
            frame_count=2,
            depth_frame_paths=depth_frames,
        )
        for frame in result.depth_frames():
            assert "_depth.png" in frame
            assert frame.count("_depth") == 1
