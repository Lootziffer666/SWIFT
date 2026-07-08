"""
Tests for core/exporter.py normal-map frame export functionality (no Blender).
"""
import pytest
import tempfile
import os
from PIL import Image
from core.exporter import export_normal_sheet, Exporter
from core.sprite_sheet import SpriteSheetManifest


def _raw(path):
    import json
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def normal_frames():
    """Create temporary RGB normal-map frames."""
    frames = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(4):
            # Tangent-space-ish normals: (128,128,255) base with per-frame tint
            img = Image.new("RGB", (32, 32), (128, 128 + i * 10, 255))
            path = os.path.join(tmpdir, f"normal_{i:02d}.png")
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


class TestExportNormalSheet:
    def test_export_normal_sheet_basic(self, normal_frames):
        """export_normal_sheet should pack RGB frames into a sheet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "normal_sheet.png")
            result = export_normal_sheet(normal_frames, out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"
            assert sheet.size == (128, 32)

    def test_export_normal_sheet_with_columns(self, normal_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "normal_sheet_2col.png")
            result = export_normal_sheet(normal_frames, out_path, columns=2)

            sheet = Image.open(result)
            assert sheet.size == (64, 64)

    def test_export_normal_sheet_empty_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "empty.png")
            with pytest.raises(ValueError, match="No frames"):
                export_normal_sheet([], out_path)


class TestExporterNormalSupport:
    def test_exporter_with_normal_frames(self, color_frames, normal_frames):
        exporter = Exporter(color_frames, fps=12, normal_frame_paths=normal_frames)
        assert exporter.normal_frame_paths == normal_frames

    def test_exporter_without_normal_frames(self, color_frames):
        exporter = Exporter(color_frames, fps=12)
        assert exporter.normal_frame_paths == []

    def test_exporter_to_normal_sheet(self, color_frames, normal_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, normal_frame_paths=normal_frames)
            out_path = os.path.join(tmpdir, "normal.png")
            result = exporter.to_normal_sheet(out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"

    def test_exporter_to_normal_sheet_without_frames_raises(self, color_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12)
            out_path = os.path.join(tmpdir, "normal.png")
            with pytest.raises(ValueError, match="No normal frames"):
                exporter.to_normal_sheet(out_path)

    def test_exporter_manifest_with_normal_paths(self, color_frames, normal_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, normal_frame_paths=normal_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path, animation_name="idle")

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert manifest.normal_frame_rects is not None
            assert len(manifest.normal_frame_rects) == 4
            assert manifest.normal_source_w > 0
            assert manifest.normal_source_h > 0

    def test_exporter_manifest_normal_rects_match_color_rects(self, color_frames, normal_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, normal_frame_paths=normal_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path)

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert set(manifest.frame_rects.keys()) == set(manifest.normal_frame_rects.keys())
            for fid in manifest.frame_rects.keys():
                assert manifest.frame_rects[fid] == manifest.normal_frame_rects[fid]


class TestNormalRoundTripWithRealFrames:
    """Non-Blender: pack real fake normal PNG frames and round-trip the manifest."""

    def _make_frames(self, tmpdir, suffix, mode, values):
        paths = []
        for i, v in enumerate(values):
            img = Image.new(mode, (32, 32), v)
            p = os.path.join(tmpdir, f"frame_{i:04d}_{suffix}.png")
            img.save(p, "PNG")
            paths.append(p)
        return paths

    def test_normal_sheet_and_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            normal_paths = self._make_frames(tmpdir, "normal", "RGB",
                                             [(128, 128, 255), (130, 128, 255),
                                              (128, 130, 255), (130, 130, 255)])
            color_paths = self._make_frames(tmpdir, "color", "RGBA",
                                            [(255, 0, 0, 255), (0, 255, 0, 255),
                                             (0, 0, 255, 255), (255, 255, 0, 255)])

            exporter = Exporter(color_paths, normal_frame_paths=normal_paths)
            normal_sheet = os.path.join(tmpdir, "out_normal.png")
            manifest_path = os.path.join(tmpdir, "out_manifest.json")

            result = exporter.to_normal_sheet(normal_sheet)
            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"
            assert sheet.size == (128, 32)

            exporter.to_manifest(manifest_path, normal_image="out_normal.png")

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert manifest.normal_image == "out_normal.png"
            assert "normalImage" in _raw(manifest_path)
            assert manifest.normal_frame_rects
            assert len(manifest.normal_frame_rects) == 4
            assert manifest.normal_source_w == 128
            assert manifest.normal_source_h == 32
