"""
Tests for core.exporter.export_manifest — verifies the auto-generated manifest
round-trips through SpriteSheetManifest and matches the sprite sheet packed by
export_sprite_sheet for the same frames (same rects, same sheet size).
"""
import json
import os

import pytest
from PIL import Image


def _make_frames(tmp_path, count, size=(32, 40)):
    paths = []
    for i in range(count):
        img = Image.new("RGBA", size, (i * 10 % 255, 0, 0, 255))
        p = str(tmp_path / f"frame_{i:04d}.png")
        img.save(p, "PNG")
        paths.append(p)
    return paths


class TestExportManifest:
    def test_manifest_round_trips_via_sprite_sheet_manifest(self, tmp_path):
        from core.exporter import export_manifest
        from core.sprite_sheet import SpriteSheetManifest

        frames = _make_frames(tmp_path, 5)
        out_path = str(tmp_path / "walk_manifest.json")
        export_manifest(frames, out_path, anim_name="walk", fps=8, loop=True)

        m = SpriteSheetManifest.from_file(out_path)
        assert len(m.frame_ids) == 5
        assert "walk" in m.animations
        assert m.animations["walk"].frames == m.frame_ids
        assert m.animations["walk"].fps == 8
        assert m.animations["walk"].loop is True

    def test_manifest_rects_match_packed_sheet(self, tmp_path):
        from core.exporter import export_manifest, export_sprite_sheet
        from core.sprite_sheet import SpriteSheetManifest

        frames = _make_frames(tmp_path, 4, size=(20, 30))
        sheet_path = str(tmp_path / "sheet.png")
        manifest_path = str(tmp_path / "sheet_manifest.json")

        export_sprite_sheet(frames, sheet_path)
        export_manifest(frames, manifest_path, anim_name="idle", fps=12)

        sheet_img = Image.open(sheet_path)
        m = SpriteSheetManifest.from_file(manifest_path)

        assert (m.source_w, m.source_h) == sheet_img.size
        # default single-row packing: 4 frames of width 20 side by side
        assert m.frame_rects["F01"] == (0, 0, 20, 30)
        assert m.frame_rects["F02"] == (20, 0, 20, 30)
        assert m.frame_rects["F04"] == (60, 0, 20, 30)

    def test_manifest_with_columns(self, tmp_path):
        from core.exporter import export_manifest
        from core.sprite_sheet import SpriteSheetManifest

        frames = _make_frames(tmp_path, 6, size=(10, 10))
        out_path = str(tmp_path / "grid_manifest.json")
        export_manifest(frames, out_path, anim_name="spin", fps=10, columns=3)

        m = SpriteSheetManifest.from_file(out_path)
        assert m.frame_rects["F01"] == (0, 0, 10, 10)
        assert m.frame_rects["F04"] == (0, 10, 10, 10)  # second row starts at col 1

    def test_empty_frames_raises(self, tmp_path):
        from core.exporter import export_manifest

        with pytest.raises(ValueError):
            export_manifest([], str(tmp_path / "empty.json"), anim_name="none")

    def test_exporter_to_manifest(self, tmp_path):
        from core.exporter import Exporter
        from core.sprite_sheet import SpriteSheetManifest

        frames = _make_frames(tmp_path, 3)
        exporter = Exporter(frames, fps=6)
        out_path = str(tmp_path / "exp_manifest.json")
        exporter.to_manifest(out_path, animation_name="run", loop=False)

        m = SpriteSheetManifest.from_file(out_path)
        assert m.animations["run"].fps == 6
        assert m.animations["run"].loop is False
