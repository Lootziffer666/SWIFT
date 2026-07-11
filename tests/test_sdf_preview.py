"""Tests for core.sdf_preview — the Blender-free --skeleton-generator path.

Integrates core.procedural.character_def + core.sdf into the standard
Exporter/manifest pipeline; these tests keep resolutions tiny so the pure-
Python raymarcher stays fast in CI.
"""
import json
import os
import tempfile

from core.procedural.skeleton import create_humanoid_skeleton
from core.sdf_preview import (
    bone_world_positions,
    export_sdf_preview,
    render_idle_frames,
)
from core.sprite_sheet import SpriteSheetManifest


class TestBoneWorldPositions:
    def test_offsets_accumulate_along_hierarchy(self):
        skel = create_humanoid_skeleton()
        pos = bone_world_positions(skel)
        assert pos["Hips"].y == 0
        assert abs(pos["Spine"].y - 0.15) < 1e-9
        assert abs(pos["Chest"].y - 0.27) < 1e-9  # 0.15 + 0.12

    def test_feet_below_hips_hands_outside_shoulders(self):
        skel = create_humanoid_skeleton()
        pos = bone_world_positions(skel)
        assert pos["Foot.L"].y < pos["Hips"].y
        assert pos["Foot.R"].y < pos["Hips"].y
        assert pos["Hand.L"].x < pos["Shoulder.L"].x
        assert pos["Hand.R"].x > pos["Shoulder.R"].x


class TestRenderIdleFrames:
    def test_frames_are_rgba_with_character_and_transparency(self):
        frames = render_idle_frames(frame_count=2, frame_size=(24, 32), max_steps=48)
        assert len(frames) == 2
        for f in frames:
            assert f.mode == "RGBA"
            lo, hi = f.getchannel("A").getextrema()
            assert lo == 0, "background must be fully transparent"
            assert hi == 255, "character must be rendered opaque"

    def test_frames_differ_across_pose_phases(self):
        frames = render_idle_frames(frame_count=2, frame_size=(24, 32), max_steps=48)
        assert frames[0].tobytes() != frames[1].tobytes()


class TestExportSdfPreview:
    def test_manifest_is_canonical_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "preview.png")
            result = export_sdf_preview(
                out, frame_count=2, frame_size=(24, 32), max_steps=48, depth_pass=True
            )
            assert os.path.exists(result["sheet_path"])
            assert os.path.exists(result["manifest_path"])
            assert os.path.exists(result["depth_path"])

            with open(result["manifest_path"]) as f:
                data = json.load(f)
            assert data["mappingVersion"] == "1.4.0"
            # Object-form rects — the only shape SHADED's actor loader accepts.
            first = next(iter(data["frameRects"].values()))
            assert set(first) == {"x", "y", "w", "h"}
            assert data["depthImage"] == os.path.basename(result["depth_path"])

            m = SpriteSheetManifest.from_dict(data)
            assert "idle" in m.animations
            assert len(m.frame_ids) == 2
