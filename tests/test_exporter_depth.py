"""
Tests for core/exporter.py depth frame export functionality.
"""
import pytest
import tempfile
import os
from PIL import Image
from core.exporter import export_depth_sheet, Exporter
from core.sprite_sheet import SpriteSheetManifest


@pytest.fixture
def depth_frames():
    """Create temporary grayscale depth frames."""
    frames = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(4):
            # Create 32x32 grayscale depth map with gradient
            img = Image.new("L", (32, 32), i * 60)  # 0, 60, 120, 180
            path = os.path.join(tmpdir, f"depth_{i:02d}.png")
            img.save(path, "PNG")
            frames.append(path)
        yield frames


@pytest.fixture
def color_frames():
    """Create temporary RGBA color frames."""
    frames = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(4):
            colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)]
            img = Image.new("RGBA", (32, 32), colors[i])
            path = os.path.join(tmpdir, f"frame_{i:02d}.png")
            img.save(path, "PNG")
            frames.append(path)
        yield frames


class TestExportDepthSheet:
    def test_export_depth_sheet_basic(self, depth_frames):
        """export_depth_sheet should pack grayscale frames into a sheet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "depth_sheet.png")
            result = export_depth_sheet(depth_frames, out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "L"  # Grayscale
            # 4 frames in single row: 32*4=128 wide, 32 tall
            assert sheet.size == (128, 32)

    def test_export_depth_sheet_with_columns(self, depth_frames):
        """export_depth_sheet with columns should arrange frames in grid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "depth_sheet_2col.png")
            result = export_depth_sheet(depth_frames, out_path, columns=2)

            sheet = Image.open(result)
            # 4 frames in 2 columns: 32*2=64 wide, 32*2=64 tall
            assert sheet.size == (64, 64)

    def test_export_depth_sheet_empty_raises(self):
        """export_depth_sheet with no frames should raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "empty.png")
            with pytest.raises(ValueError, match="No depth frames"):
                export_depth_sheet([], out_path)

    def test_depth_sheet_pixel_values_preserved(self, depth_frames):
        """Pixel values in depth sheet should match source frames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "depth_sheet.png")
            export_depth_sheet(depth_frames, out_path)

            sheet = Image.open(out_path)
            pixels = sheet.load()

            # Check corners of each frame (in single row layout)
            # Frame 0 at (0,0): value 0
            assert pixels[0, 0] == 0
            # Frame 1 at (32,0): value 60
            assert pixels[32, 0] == 60
            # Frame 2 at (64,0): value 120
            assert pixels[64, 0] == 120
            # Frame 3 at (96,0): value 180
            assert pixels[96, 0] == 180


class TestExporterDepthSupport:
    def test_exporter_with_depth_frames(self, color_frames, depth_frames):
        """Exporter should accept depth_frame_paths in constructor."""
        exporter = Exporter(color_frames, fps=12, depth_frame_paths=depth_frames)
        assert exporter.depth_frame_paths == depth_frames

    def test_exporter_without_depth_frames(self, color_frames):
        """Exporter should work without depth frames (backwards compatible)."""
        exporter = Exporter(color_frames, fps=12)
        assert exporter.depth_frame_paths == []

    def test_exporter_to_depth_sheet(self, color_frames, depth_frames):
        """Exporter.to_depth_sheet() should export depth frames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, depth_frame_paths=depth_frames)
            out_path = os.path.join(tmpdir, "depth.png")
            result = exporter.to_depth_sheet(out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "L"

    def test_exporter_to_depth_sheet_without_frames_raises(self, color_frames):
        """to_depth_sheet() should raise if no depth frames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12)
            out_path = os.path.join(tmpdir, "depth.png")
            with pytest.raises(ValueError, match="No depth frames"):
                exporter.to_depth_sheet(out_path)

    def test_exporter_manifest_with_depth_paths(self, color_frames, depth_frames):
        """Exporter.to_manifest() with depth frames should include depth rects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, depth_frame_paths=depth_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path, animation_name="idle")

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert manifest.depth_frame_rects is not None
            assert len(manifest.depth_frame_rects) == 4
            assert manifest.depth_source_w > 0
            assert manifest.depth_source_h > 0

    def test_exporter_manifest_depth_rects_match_color_rects(self, color_frames, depth_frames):
        """Depth frameRects should have same coordinates as color frameRects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, depth_frame_paths=depth_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path)

            manifest = SpriteSheetManifest.from_file(manifest_path)

            # Both should have same frame IDs
            assert set(manifest.frame_rects.keys()) == set(manifest.depth_frame_rects.keys())

            # Coordinates should be identical (same layout)
            for fid in manifest.frame_rects.keys():
                assert manifest.frame_rects[fid] == manifest.depth_frame_rects[fid]


class TestManifestVersioning:
    def test_manifest_version_1_4_0_with_depth(self, color_frames, depth_frames):
        """Manifest with depth frames should use version 1.4.0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, depth_frame_paths=depth_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path)

            manifest = SpriteSheetManifest.from_file(manifest_path)
            # Check via raw JSON to verify version string
            import json
            with open(manifest_path) as f:
                data = json.load(f)
            assert data["mappingVersion"] == "1.4.0"

    def test_manifest_version_1_4_0_without_depth(self, color_frames):
        """Manifest without depth should still use 1.4.0 (forward compatible)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path)

            import json
            with open(manifest_path) as f:
                data = json.load(f)
            assert data["mappingVersion"] == "1.4.0"


class TestDepthManifestIntegration:
    def test_export_and_load_depth_manifest(self, color_frames, depth_frames):
        """Full round-trip: export manifest with depth, load it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, depth_frame_paths=depth_frames)

            # Export everything
            color_sheet = os.path.join(tmpdir, "sprite.png")
            depth_sheet = os.path.join(tmpdir, "sprite_depth.png")
            manifest_path = os.path.join(tmpdir, "manifest.json")

            exporter.to_sprite_sheet(color_sheet)
            exporter.to_depth_sheet(depth_sheet)
            exporter.to_manifest(manifest_path, depth_image="sprite_depth.png")

            # Load manifest
            manifest = SpriteSheetManifest.from_file(manifest_path)

            # Verify all components
            assert manifest.depth_image == "sprite_depth.png"
            assert len(manifest.depth_frame_rects) == len(color_frames)
            assert manifest.depth_source_w == 128
            assert manifest.depth_source_h == 32
