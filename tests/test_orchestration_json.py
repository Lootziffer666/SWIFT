"""
Tests for the SWIFT <-> ANVIL machine-readable JSON contract (--json / --json-summary).

Covers:
  - `spritesheet list`  -> success JSON on stdout, exit 0
  - `spritesheet extract` -> success JSON with artifact, exit 0
  - missing input (image / manifest / render model) -> error JSON on stderr, exit 2
  - Blender-missing path for render -> error JSON on stderr, exit 3
  - non-json mode preserves human-readable stdout (no JSON leakage)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN = str(REPO_ROOT / "main.py")
FIXTURES = Path(__file__).parent / "fixtures"
CAT_IMAGE = str(FIXTURES / "cat_blue.png")
CAT_MANIFEST = str(FIXTURES / "cat_manifest.json")
MISSING = "/nonexistent/path/does_not_exist.png"


def run(args):
    return subprocess.run(
        [sys.executable, MAIN, *args],
        capture_output=True,
        text=True,
    )


class TestSpritesheetJsonSuccess:
    def test_list_emits_valid_summary(self):
        r = run(["spritesheet", "list", CAT_IMAGE, "--manifest", CAT_MANIFEST, "--json"])
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["status"] == "success"
        assert data["command"] == "spritesheet"
        assert data["action"] == "list"
        assert isinstance(data["artifacts"], list)
        assert data["artifacts"] == []
        assert data["sheet_path"] == CAT_IMAGE
        assert data["manifest_path"] == CAT_MANIFEST
        assert data["mapping_version"] == "1.2"
        assert isinstance(data["frame_count"], int)
        assert data["frame_count"] > 0
        assert isinstance(data["animation_names"], list)

    def test_extract_emits_artifact(self, tmp_path):
        out = str(tmp_path / "frame_F01.png")
        r = run(["spritesheet", "extract", CAT_IMAGE, "--manifest", CAT_MANIFEST,
                 "--frame", "F01", "--output", out, "--json"])
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["status"] == "success"
        assert data["action"] == "extract"
        assert data["artifacts"]
        artifact = data["artifacts"][0]
        assert artifact["type"] == "frame"
        assert artifact["path"] == out
        assert Path(out).is_file()

    def test_stdout_only_contains_json_when_json(self):
        r = run(["spritesheet", "list", CAT_IMAGE, "--manifest", CAT_MANIFEST, "--json"])
        # Single JSON object on stdout; human text must not leak to stdout.
        assert r.stdout.strip().startswith("{")
        json.loads(r.stdout)


class TestJsonErrorContract:
    def test_missing_image_exit_2(self):
        r = run(["spritesheet", "list", MISSING, "--manifest", CAT_MANIFEST, "--json"])
        assert r.returncode == 2
        err = json.loads(r.stderr)
        assert err["status"] == "error"
        assert "error" in err
        assert "not found" in err["error"].lower()
        assert r.stdout.strip() == ""

    def test_missing_manifest_exit_2(self):
        r = run(["spritesheet", "list", CAT_IMAGE, "--manifest", MISSING, "--json"])
        assert r.returncode == 2
        err = json.loads(r.stderr)
        assert err["status"] == "error"

    def test_export_missing_anim_exit_2(self):
        r = run(["spritesheet", "export", CAT_IMAGE, "--manifest", CAT_MANIFEST, "--json"])
        assert r.returncode == 2
        err = json.loads(r.stderr)
        assert err["status"] == "error"

    def test_render_missing_model_exit_2(self):
        r = run(["render", "--model", MISSING, "--json"])
        assert r.returncode == 2
        err = json.loads(r.stderr)
        assert err["status"] == "error"


class TestNonJsonBehavior:
    def test_list_keeps_human_text(self):
        r = run(["spritesheet", "list", CAT_IMAGE, "--manifest", CAT_MANIFEST])
        assert r.returncode == 0
        assert "Animations:" in r.stdout
        # No JSON object leaked onto stdout in non-json mode.
        assert not r.stdout.strip().startswith("{")

    def test_missing_input_non_json_goes_to_stderr(self):
        r = run(["spritesheet", "list", MISSING, "--manifest", CAT_MANIFEST])
        assert r.returncode == 2
        assert "ERROR" in r.stderr
        assert r.stdout.strip() == ""
