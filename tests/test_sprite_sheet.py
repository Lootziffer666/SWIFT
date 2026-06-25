"""
Tests for SpriteSheetManifest and SpriteSheet.

Uses:
 - A synthetic 1536×523 test image built at exact manifest dimensions for precision tests
 - The real cat_blue / cat_brown fixtures for smoke tests (auto-scale path)
"""
import os
import json
import pytest
from pathlib import Path
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"
CAT_MANIFEST_PATH = str(FIXTURES / "cat_manifest.json")
CAT_BLUE_PATH = str(FIXTURES / "cat_blue.png")
CAT_BROWN_PATH = str(FIXTURES / "cat_brown.png")

# Manifest dict used across tests (same content as the JSON file)
with open(CAT_MANIFEST_PATH) as _f:
    CAT_MANIFEST_DICT = json.load(_f)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_synthetic_sheet(path: str, w: int = 1536, h: int = 523):
    """
    Create a synthetic sprite sheet at exact manifest dimensions.
    Each frame region is filled with a unique flat color so we can verify
    that the correct pixels are extracted.
    Colors cycle through a deterministic palette based on frame index.
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    manifest = CAT_MANIFEST_DICT
    rects = manifest["frameRects"]
    frames = manifest["frames"]
    for i, frame in enumerate(frames):
        fid = frame["id"]
        r = rects[fid]
        color = ((i * 37 + 50) % 200 + 55,
                 (i * 73 + 80) % 200 + 55,
                 (i * 113 + 110) % 200 + 55,
                 255)
        for x in range(r["x"], r["x"] + r["w"]):
            for y in range(r["y"], r["y"] + r["h"]):
                img.putpixel((x, y), color)
    img.save(path, "PNG")
    return path


# ─── Manifest tests ───────────────────────────────────────────────────────────

class TestSpriteSheetManifest:
    def test_from_file(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_file(CAT_MANIFEST_PATH)
        assert m.source_w == 1536
        assert m.source_h == 523

    def test_from_dict(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        assert len(m.frame_ids) == 25
        assert "F01" in m.frame_ids
        assert "F25" in m.frame_ids

    def test_frame_rects_authoritative(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        assert m.frame_rects["F01"] == (0, 0, 149, 153)
        assert m.frame_rects["F02"] == (155, 0, 148, 153)
        assert m.frame_rects["F11"] == (0, 185, 149, 153)
        assert m.frame_rects["F21"] == (0, 370, 149, 153)
        assert m.frame_rects["F25"] == (616, 370, 149, 153)

    def test_frame_keys(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        assert m.frame_keys["F01"] == "idle_stand"
        assert m.frame_keys["F24"] == "hiss_attack"
        assert m.key_to_id["walk_step_1"] == "F02"

    def test_animations_parsed(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        assert "walk" in m.animations
        assert "pounce" in m.animations
        assert "eat_cycle" in m.animations
        walk = m.animations["walk"]
        assert walk.fps == 8
        assert walk.loop is True
        assert walk.frames == ["F01", "F02", "F03", "F05", "F07"]

    def test_applies_to(self):
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        assert "cat_blue" in m.applies_to
        assert "cat_brown" in m.applies_to

    def test_grid_fallback(self):
        """Manifest without frameRects should compute rects from grid."""
        from core.sprite_sheet import SpriteSheetManifest
        data = dict(CAT_MANIFEST_DICT)
        del data["frameRects"]
        m = SpriteSheetManifest.from_dict(data)
        # Grid-computed rect for F01: col 1 → x=0, w=149; row 1 → y=0, h=153
        assert m.frame_rects["F01"] == (0, 0, 149, 153)
        # F11: col 1, row 2 → x=0, y=185
        assert m.frame_rects["F11"] == (0, 185, 149, 153)


# ─── SpriteSheet extraction (synthetic image at exact manifest dims) ──────────

class TestSpriteSheetExact:
    @pytest.fixture(autouse=True)
    def synthetic_sheet(self, tmp_path):
        self.sheet_path = str(tmp_path / "synthetic.png")
        make_synthetic_sheet(self.sheet_path)
        from core.sprite_sheet import SpriteSheetManifest, SpriteSheet
        manifest = SpriteSheetManifest.from_dict(CAT_MANIFEST_DICT)
        self.sheet = SpriteSheet(self.sheet_path, manifest)

    def test_extract_frame_size(self):
        frame = self.sheet.extract_frame("F01")
        assert frame.size == (149, 153)

    def test_extract_frame_f02_size(self):
        frame = self.sheet.extract_frame("F02")
        assert frame.size == (148, 153)

    def test_extract_frame_by_key(self):
        frame = self.sheet.extract_frame_by_key("idle_stand")
        assert frame.size == (149, 153)

    def test_extract_all_frames_count(self):
        all_frames = self.sheet.extract_all_frames()
        assert len(all_frames) == 25

    def test_frame_has_content(self):
        """Each frame region should have pixels (not all transparent)."""
        import numpy as np
        frame = self.sheet.extract_frame("F01")
        arr = np.array(frame)
        assert arr[:, :, 3].max() == 255  # at least some fully-opaque pixels

    def test_get_animation_walk(self):
        frames = self.sheet.get_animation("walk")
        assert len(frames) == 5
        # walk = [F01,F02,F03,F05,F07]; F02 has w=148, others w=149
        assert all(f.size[1] == 153 for f in frames)   # all same height
        assert frames[0].size == (149, 153)             # F01
        assert frames[1].size == (148, 153)             # F02 (col 2, w=148)

    def test_get_animation_eat_cycle(self):
        frames = self.sheet.get_animation("eat_cycle")
        assert len(frames) == 3

    def test_animation_fps(self):
        assert self.sheet.animation_fps("walk") == 8
        assert self.sheet.animation_fps("eat_cycle") == 6
        assert self.sheet.animation_fps("rest_idle") == 2

    def test_animation_loops(self):
        assert self.sheet.animation_loops("walk") is True
        assert self.sheet.animation_loops("pounce") is False

    def test_list_animations(self):
        anims = self.sheet.list_animations()
        for expected in ["walk", "pounce", "eat_cycle", "idle_variants", "specials"]:
            assert expected in anims

    def test_unknown_frame_raises(self):
        with pytest.raises(KeyError):
            self.sheet.extract_frame("F99")

    def test_unknown_animation_raises(self):
        with pytest.raises(KeyError):
            self.sheet.get_animation("nonexistent")

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            self.sheet.extract_frame_by_key("does_not_exist")

    def test_export_animation_gif(self, tmp_path):
        out = str(tmp_path / "walk.gif")
        result = self.sheet.export_animation_gif("walk", out)
        assert os.path.isfile(result)
        gif = Image.open(result)
        assert gif.format == "GIF"

    def test_export_animation_sheet(self, tmp_path):
        out = str(tmp_path / "walk_sheet.png")
        result = self.sheet.export_animation_sheet("walk", out, columns=5)
        assert os.path.isfile(result)
        sheet = Image.open(result)
        # 5 frames × 149px wide = 745px; height = 153px
        assert sheet.size == (745, 153)

    def test_scale_is_1_at_exact_dims(self):
        assert abs(self.sheet._scale_x - 1.0) < 0.01
        assert abs(self.sheet._scale_y - 1.0) < 0.01


# ─── SpriteSheet with real cat assets (smoke tests) ──────────────────────────

class TestSpriteSheetRealAssets:
    @pytest.fixture(autouse=True)
    def load_manifest(self):
        from core.sprite_sheet import SpriteSheetManifest
        self.manifest = SpriteSheetManifest.from_file(CAT_MANIFEST_PATH)

    def test_cat_blue_loads(self):
        from core.sprite_sheet import SpriteSheet
        sheet = SpriteSheet(CAT_BLUE_PATH, self.manifest)
        assert sheet._scale_x > 0
        assert sheet._scale_y > 0

    def test_cat_brown_loads(self):
        from core.sprite_sheet import SpriteSheet
        sheet = SpriteSheet(CAT_BROWN_PATH, self.manifest)
        assert sheet._scale_x > 0
        assert sheet._scale_y > 0

    def test_shared_manifest_both_variants(self):
        """One manifest object can drive two different color variant sheets."""
        from core.sprite_sheet import SpriteSheet
        blue = SpriteSheet(CAT_BLUE_PATH, self.manifest)
        brown = SpriteSheet(CAT_BROWN_PATH, self.manifest)
        assert blue.list_animations() == brown.list_animations()

    def test_extract_frame_scaled_has_content(self):
        """Real asset: F01 extracted at scaled coords should have non-zero pixels."""
        import numpy as np
        from core.sprite_sheet import SpriteSheet
        sheet = SpriteSheet(CAT_BLUE_PATH, self.manifest)
        # F01 is row 1 col 1 — scaled frame should have some opaque pixels
        frame = sheet.extract_frame("F01")
        assert frame.size[0] > 0 and frame.size[1] > 0
        arr = np.array(frame)
        # Sheet has transparent background with cat content → some pixels non-transparent
        assert arr[:, :, 3].sum() > 0

    def test_cat_walk_gif_export(self, tmp_path):
        from core.sprite_sheet import SpriteSheet
        sheet = SpriteSheet(CAT_BLUE_PATH, self.manifest)
        out = str(tmp_path / "cat_walk.gif")
        result = sheet.export_animation_gif("walk", out)
        assert os.path.isfile(result)
        gif = Image.open(result)
        assert gif.format == "GIF"

    def test_cat_pounce_sheet_export(self, tmp_path):
        from core.sprite_sheet import SpriteSheet
        sheet = SpriteSheet(CAT_BROWN_PATH, self.manifest)
        out = str(tmp_path / "cat_pounce.png")
        result = sheet.export_animation_sheet("pounce", out)
        assert os.path.isfile(result)
        img = Image.open(result)
        # pounce has 4 frames in a row
        assert img.size[0] > img.size[1]
