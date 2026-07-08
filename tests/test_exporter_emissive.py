"""
Tests for core/exporter.py emissive frame export functionality (no Blender).
"""
import pytest
import tempfile
import os
from PIL import Image
from core.exporter import export_emissive_sheet, Exporter
from core.sprite_sheet import SpriteSheetManifest


def _raw(path):
    import json
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def emissive_frames():
    """Create temporary RGB emissive frames."""
    frames = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(4):
            # Glow values increasing per frame
            img = Image.new("RGB", (32, 32), (i * 40, 0, 255 - i * 40))
            path = os.path.join(tmpdir, f"emissive_{i:02d}.png")
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


class TestExportEmissiveSheet:
    def test_export_emissive_sheet_basic(self, emissive_frames):
        """export_emissive_sheet should pack RGB frames into a sheet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "emissive_sheet.png")
            result = export_emissive_sheet(emissive_frames, out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"
            assert sheet.size == (128, 32)

    def test_export_emissive_sheet_with_columns(self, emissive_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "emissive_sheet_2col.png")
            result = export_emissive_sheet(emissive_frames, out_path, columns=2)

            sheet = Image.open(result)
            assert sheet.size == (64, 64)

    def test_export_emissive_sheet_empty_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "empty.png")
            with pytest.raises(ValueError, match="No frames"):
                export_emissive_sheet([], out_path)


class TestExporterEmissiveSupport:
    def test_exporter_with_emissive_frames(self, color_frames, emissive_frames):
        exporter = Exporter(color_frames, fps=12, emissive_frame_paths=emissive_frames)
        assert exporter.emissive_frame_paths == emissive_frames

    def test_exporter_without_emissive_frames(self, color_frames):
        exporter = Exporter(color_frames, fps=12)
        assert exporter.emissive_frame_paths == []

    def test_exporter_to_emissive_sheet(self, color_frames, emissive_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, emissive_frame_paths=emissive_frames)
            out_path = os.path.join(tmpdir, "emissive.png")
            result = exporter.to_emissive_sheet(out_path)

            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"

    def test_exporter_to_emissive_sheet_without_frames_raises(self, color_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12)
            out_path = os.path.join(tmpdir, "emissive.png")
            with pytest.raises(ValueError, match="No emissive frames"):
                exporter.to_emissive_sheet(out_path)

    def test_exporter_manifest_with_emissive_paths(self, color_frames, emissive_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, emissive_frame_paths=emissive_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path, animation_name="idle")

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert manifest.emissive_frame_rects is not None
            assert len(manifest.emissive_frame_rects) == 4
            assert manifest.emissive_source_w > 0
            assert manifest.emissive_source_h > 0

    def test_exporter_manifest_emissive_rects_match_color_rects(self, color_frames, emissive_frames):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = Exporter(color_frames, fps=12, emissive_frame_paths=emissive_frames)
            manifest_path = os.path.join(tmpdir, "manifest.json")
            exporter.to_manifest(manifest_path)

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert set(manifest.frame_rects.keys()) == set(manifest.emissive_frame_rects.keys())
            for fid in manifest.frame_rects.keys():
                assert manifest.frame_rects[fid] == manifest.emissive_frame_rects[fid]


class TestEmissiveRoundTripWithRealFrames:
    """Non-Blender: pack real fake emissive PNG frames and round-trip the manifest."""

    def _make_frames(self, tmpdir, suffix, mode, values):
        paths = []
        for i, v in enumerate(values):
            img = Image.new(mode, (32, 32), v)
            p = os.path.join(tmpdir, f"frame_{i:04d}_{suffix}.png")
            img.save(p, "PNG")
            paths.append(p)
        return paths

    def test_emissive_sheet_and_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            emissive_paths = self._make_frames(tmpdir, "emissive", "RGB",
                                               [(40, 0, 215), (80, 0, 175),
                                                (120, 0, 135), (160, 0, 95)])
            color_paths = self._make_frames(tmpdir, "color", "RGBA",
                                            [(255, 0, 0, 255), (0, 255, 0, 255),
                                             (0, 0, 255, 255), (255, 255, 0, 255)])

            exporter = Exporter(color_paths, emissive_frame_paths=emissive_paths)
            emissive_sheet = os.path.join(tmpdir, "out_emissive.png")
            manifest_path = os.path.join(tmpdir, "out_manifest.json")

            result = exporter.to_emissive_sheet(emissive_sheet)
            assert os.path.isfile(result)
            sheet = Image.open(result)
            assert sheet.mode == "RGB"
            assert sheet.size == (128, 32)

            exporter.to_manifest(manifest_path, emissive_image="out_emissive.png")

            manifest = SpriteSheetManifest.from_file(manifest_path)
            assert manifest.emissive_image == "out_emissive.png"
            assert "emissiveImage" in _raw(manifest_path)
            assert manifest.emissive_frame_rects
            assert len(manifest.emissive_frame_rects) == 4
            assert manifest.emissive_source_w == 128
            assert manifest.emissive_source_h == 32
