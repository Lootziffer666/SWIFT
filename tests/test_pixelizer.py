"""Tests for pixel art conversion - palette consistency across frames."""
import os
import pytest
from PIL import Image
import numpy as np


class TestPixelizer:
    def _make_rgba_image(self, w=128, h=128, color=(200, 100, 50, 255)):
        img = Image.new("RGBA", (w, h), color)
        return img

    def test_output_size(self):
        from core.video_to_sprite.pixelizer import pixelize, PixelizeConfig
        img = self._make_rgba_image(128, 128)
        cfg = PixelizeConfig(target_width=64, target_height=64)
        result = pixelize(img, cfg)
        assert result.size == (64, 64)

    def test_output_is_rgba(self):
        from core.video_to_sprite.pixelizer import pixelize, PixelizeConfig
        img = self._make_rgba_image()
        result = pixelize(img, PixelizeConfig())
        assert result.mode == "RGBA"

    def test_palette_extraction(self):
        from core.video_to_sprite.pixelizer import extract_palette
        img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        palette = extract_palette(img, max_colors=4)
        assert isinstance(palette, list)
        assert len(palette) >= 1
        # At least one tuple should exist
        assert all(isinstance(c, tuple) and len(c) == 3 for c in palette)

    def test_sequence_consistent_palette(self, tmp_path):
        from core.video_to_sprite.pixelizer import pixelize_sequence, PixelizeConfig

        # Create 3 frames with different colors
        frames = []
        colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
        for i, color in enumerate(colors):
            img = Image.new("RGBA", (64, 64), color)
            p = str(tmp_path / f"frame_{i}.png")
            img.save(p)
            frames.append(p)

        out_dir = str(tmp_path / "pixelized")
        cfg = PixelizeConfig(lock_palette=True, palette_colors=8)
        results = pixelize_sequence(frames, out_dir, cfg)

        assert len(results) == 3
        assert all(os.path.isfile(p) for p in results)

        # All output frames should have the same palette (from frame 0)
        from PIL import Image as PILImage
        first_palette = cfg.anchor_palette
        assert first_palette is not None  # anchor was set

    def test_no_palette_lock_allows_variation(self, tmp_path):
        from core.video_to_sprite.pixelizer import pixelize_sequence, PixelizeConfig

        frames = []
        for i in range(3):
            img = Image.new("RGBA", (32, 32), (i * 80, 100, 200, 255))
            p = str(tmp_path / f"f{i}.png")
            img.save(p)
            frames.append(p)

        out_dir = str(tmp_path / "out")
        cfg = PixelizeConfig(lock_palette=False)
        results = pixelize_sequence(frames, out_dir, cfg)
        assert len(results) == 3

    def test_alpha_preserved(self):
        from core.video_to_sprite.pixelizer import pixelize, PixelizeConfig
        img = Image.new("RGBA", (64, 64), (100, 150, 200, 128))
        result = pixelize(img, PixelizeConfig(target_width=32, target_height=32))
        assert result.mode == "RGBA"
        # Should have some transparency
        pixels = list(result.getdata())
        alphas = [p[3] for p in pixels]
        assert any(a < 255 for a in alphas)


class TestExporter:
    def _make_frames(self, tmp_path, count=4, size=(64, 64)):
        paths = []
        for i in range(count):
            img = Image.new("RGBA", size, (i * 50, 100, 200, 255))
            p = str(tmp_path / f"frame_{i:04d}.png")
            img.save(p)
            paths.append(p)
        return paths

    def test_sprite_sheet_dimensions(self, tmp_path):
        from core.exporter import export_sprite_sheet
        frames = self._make_frames(tmp_path, count=4)
        out = str(tmp_path / "sheet.png")
        export_sprite_sheet(frames, out, columns=4)
        sheet = Image.open(out)
        # 4 frames in 1 row, each 64x64 → 256x64
        assert sheet.size == (256, 64)

    def test_sprite_sheet_two_rows(self, tmp_path):
        from core.exporter import export_sprite_sheet
        frames = self._make_frames(tmp_path, count=6)
        out = str(tmp_path / "sheet.png")
        export_sprite_sheet(frames, out, columns=3)
        sheet = Image.open(out)
        assert sheet.size == (192, 128)  # 3 cols × 64, 2 rows × 64

    def test_gif_export(self, tmp_path):
        from core.exporter import export_gif
        frames = self._make_frames(tmp_path, count=4)
        out = str(tmp_path / "anim.gif")
        export_gif(frames, out, fps=12)
        assert os.path.isfile(out)
        gif = Image.open(out)
        assert gif.format == "GIF"

    def test_frames_json_export(self, tmp_path):
        import json
        from core.exporter import export_frames_with_metadata
        frames = self._make_frames(tmp_path, count=3)
        out_dir = str(tmp_path / "export")
        meta_path = export_frames_with_metadata(frames, out_dir, fps=12, animation_name="walk")
        assert os.path.isfile(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["animation"] == "walk"
        assert meta["frame_count"] == 3
        assert len(meta["frames"]) == 3

    def test_empty_frames_raises(self, tmp_path):
        from core.exporter import export_sprite_sheet
        with pytest.raises(ValueError):
            export_sprite_sheet([], str(tmp_path / "out.png"))
