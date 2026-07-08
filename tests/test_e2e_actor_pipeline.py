"""
End-to-end test for the SHADED-ready actor pipeline harness.

Runs the COMPLETE SWIFT actor-production path (scripts/demo_actor_pipeline.py)
end-to-end using a synthetic fixture so it works without Blender, and asserts:
  - the produced manifest is SHADED.addActor-compatible (required keys +
    a simulated addActor call records a well-formed object), and
  - the manifest round-trips (write -> read -> write, structure equality).
"""
import json

import pytest


@pytest.fixture
def pipeline():
    from scripts import demo_actor_pipeline as m
    return m


class TestE2EActorPipeline:
    def test_pipeline_emits_shaded_ready_actor(self, pipeline, tmp_path):
        out = str(tmp_path / "actor")
        summary = pipeline.build_actor_pipeline(
            output_dir=out,
            frame_count=6,
            fps=12,
            anim_name="idle",
            world_state_names=("dust", "aging", "heat", "soot"),
            intensity=0.6,
        )

        # Manifest + sheet + one PNG variant per world state exist.
        assert (tmp_path / "actor" / "idle_manifest.json").is_file()
        assert (tmp_path / "actor" / "idle_sheet.png").is_file()
        for state in ("dust", "aging", "heat", "soot"):
            assert (tmp_path / "actor" / f"idle_{state}.png").is_file()

        assert summary["frame_count"] == 6
        assert summary["fps"] == 12
        assert summary["anim_name"] == "idle"
        assert set(summary["world_states"]) == {"dust", "aging", "heat", "soot"}
        assert len(summary["artifacts"]) >= 6 + 4  # frames + sheet + variants + manifest

    def test_addactor_compatibility(self, pipeline, tmp_path):
        out = str(tmp_path / "actor")
        summary = pipeline.build_actor_pipeline(
            output_dir=out, frame_count=6, anim_name="idle",
            world_state_names=("dust", "aging", "heat", "soot"),
        )

        shaded = pipeline.MockSHADED()
        manifest, anim_name = pipeline.validate_addactor_compatible(
            summary["manifest_path"], shaded, depth_layer="mid"
        )

        # Required manifest keys present.
        for key in pipeline.REQUIRED_MANIFEST_KEYS:
            assert key in manifest, f"manifest missing {key!r}"
        assert manifest["mappingVersion"] == "1.4.0"

        # SHADED stub recorded exactly one well-formed addActor call.
        assert len(shaded.calls) == 1
        call = shaded.calls[0]
        assert call["anim"] == "idle"
        assert call["depthLayer"] == "mid"
        assert call["x"] == 0.5 and call["y"] == 0.5
        assert call["scale"] == 1.0
        assert isinstance(call["manifest"], dict)
        assert call["manifest"] is manifest

    def test_manifest_round_trip(self, pipeline, tmp_path):
        out = str(tmp_path / "actor")
        summary = pipeline.build_actor_pipeline(
            output_dir=out, frame_count=5, anim_name="walk",
            world_state_names=("dust", "aging"),
        )
        roundtrip_path = pipeline.validate_manifest_roundtrip(summary["manifest_path"])
        with open(summary["manifest_path"]) as f:
            original = json.load(f)
        with open(roundtrip_path) as f:
            written = json.load(f)
        assert original == written

    def test_optional_depth_sheet(self, pipeline, tmp_path):
        out = str(tmp_path / "actor")
        summary = pipeline.build_actor_pipeline(
            output_dir=out, frame_count=4, anim_name="idle",
            world_state_names=("dust",), depth=True,
        )
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_file(summary["manifest_path"])
        assert m.depth_image is not None
        assert m.depth_frame_rects, "depth frame rects should be present when depth=True"
        assert set(m.world_states.keys()) == {"dust"}

    def test_world_state_variant_pngs_match_manifest(self, pipeline, tmp_path):
        out = str(tmp_path / "actor")
        summary = pipeline.build_actor_pipeline(
            output_dir=out, frame_count=4, anim_name="idle",
            world_state_names=("dust", "aging", "heat", "soot"),
        )
        from core.sprite_sheet import SpriteSheetManifest
        m = SpriteSheetManifest.from_file(summary["manifest_path"])
        assert set(m.world_states.keys()) == set(summary["world_states"])
        for name, ref in m.world_states.items():
            variant_file = tmp_path / "actor" / ref.variant_path
            assert variant_file.is_file(), f"variant PNG missing for {name}"
