"""
Tests for BlenderBridge - uses mocks so Blender doesn't need to be installed.
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
from core.blender_bridge import BlenderBridge, RenderJob, RenderResult, find_blender


class TestFindBlender:
    def test_env_override(self, tmp_path):
        fake_blender = tmp_path / "blender.exe"
        fake_blender.write_text("")
        with patch.dict(os.environ, {"SWIFT_BLENDER_PATH": str(fake_blender)}):
            path = find_blender()
        assert path == str(fake_blender)

    def test_direct_override(self, tmp_path):
        fake = tmp_path / "blender"
        fake.write_text("")
        assert find_blender(str(fake)) == str(fake)

    def test_not_found_raises(self):
        with patch.dict(os.environ, {"SWIFT_BLENDER_PATH": ""}):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", return_value=False):
                    with pytest.raises(FileNotFoundError):
                        find_blender()


class TestRenderJob:
    def test_validate_missing_char(self):
        job = RenderJob(char_fbx="/nonexistent/char.fbx")
        with pytest.raises(FileNotFoundError):
            job.validate()

    def test_validate_missing_anim(self, tmp_path):
        char = tmp_path / "char.fbx"
        char.write_text("stub")
        job = RenderJob(
            char_fbx=str(char),
            anim_fbx="/nonexistent/walk.fbx",
        )
        with pytest.raises(FileNotFoundError):
            job.validate()

    def test_validate_ok(self, tmp_path):
        char = tmp_path / "char.fbx"
        char.write_text("stub")
        job = RenderJob(char_fbx=str(char))
        job.validate()  # should not raise


class TestBlenderBridge:
    def _make_success_frames(self, tmp_path, count=8):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        for i in range(count):
            (frames_dir / f"frame_{i:04d}.png").write_bytes(b"PNG")
        meta = {
            "frame_count": count,
            "width": 64,
            "height": 64,
            "fps": 12,
        }
        (frames_dir / "meta.json").write_text(json.dumps(meta))
        return frames_dir

    def test_render_success(self, tmp_path):
        char = tmp_path / "char.fbx"
        char.write_text("stub")
        frames_dir = self._make_success_frames(tmp_path)

        mock_proc = MagicMock()
        mock_proc.stdout = iter(["Blender 4.2", "SWIFT: Rendered 8 frames"])
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock()

        bridge = BlenderBridge(blender_path="/fake/blender")

        with patch("subprocess.Popen", return_value=mock_proc):
            with patch("core.blender_bridge.find_blender", return_value="/fake/blender"):
                job = RenderJob(
                    char_fbx=str(char),
                    out_dir=str(frames_dir),
                )
                result = bridge.render(job)

        assert result.success
        assert result.frame_count == 8

    def test_render_blender_not_found(self, tmp_path):
        char = tmp_path / "char.fbx"
        char.write_text("stub")

        bridge = BlenderBridge(blender_path="/nonexistent/blender")

        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            with patch("core.blender_bridge.find_blender", return_value="/nonexistent/blender"):
                job = RenderJob(char_fbx=str(char))
                result = bridge.render(job)

        assert not result.success
        assert "not found" in result.error

    def test_render_failure_nonzero_exit(self, tmp_path):
        char = tmp_path / "char.fbx"
        char.write_text("stub")

        mock_proc = MagicMock()
        mock_proc.stdout = iter(["Error: import failed"])
        mock_proc.returncode = 1
        mock_proc.wait = MagicMock()

        bridge = BlenderBridge(blender_path="/fake/blender")

        with patch("subprocess.Popen", return_value=mock_proc):
            with patch("core.blender_bridge.find_blender", return_value="/fake/blender"):
                job = RenderJob(char_fbx=str(char), out_dir=str(tmp_path))
                result = bridge.render(job)

        assert not result.success

    def test_check_blender_success(self):
        bridge = BlenderBridge()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Blender 4.2.0\nbuild date: 2024",
                returncode=0,
            )
            with patch("core.blender_bridge.find_blender", return_value="/fake/blender"):
                ok, version = bridge.check_blender()
        assert ok
        assert "Blender" in version
