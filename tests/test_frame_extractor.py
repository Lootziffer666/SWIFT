"""Tests for frame extractor - uses synthetic video created with OpenCV."""
import os
import numpy as np
import pytest

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


pytestmark = pytest.mark.skipif(not CV2_AVAILABLE, reason="opencv-python not installed")


def _create_test_video(path: str, frame_count: int = 12, w: int = 64, h: int = 64, fps: float = 12.0):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for i in range(frame_count):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :, 0] = int(i * 255 / frame_count)  # varying red channel
        out.write(frame)
    out.release()


class TestFrameExtractor:
    def test_extract_all_frames(self, tmp_path):
        from core.video_to_sprite.frame_extractor import extract_frames

        video_path = str(tmp_path / "test.mp4")
        out_dir = str(tmp_path / "frames")
        _create_test_video(video_path, frame_count=8)

        result = extract_frames(video_path, out_dir, keyframes_only=False)
        assert result.success
        assert len(result.frames) == 8
        assert all(os.path.isfile(f.path) for f in result.frames)

    def test_extract_missing_file(self, tmp_path):
        from core.video_to_sprite.frame_extractor import extract_frames

        result = extract_frames("/nonexistent.mp4", str(tmp_path / "out"))
        assert not result.success
        assert "not found" in result.error.lower()

    def test_max_frames_limit(self, tmp_path):
        from core.video_to_sprite.frame_extractor import extract_frames

        video_path = str(tmp_path / "test.mp4")
        _create_test_video(video_path, frame_count=20)
        out_dir = str(tmp_path / "frames")

        result = extract_frames(video_path, out_dir, max_frames=5)
        assert result.success
        assert len(result.frames) <= 5

    def test_frames_are_png(self, tmp_path):
        from core.video_to_sprite.frame_extractor import extract_frames

        video_path = str(tmp_path / "test.mp4")
        _create_test_video(video_path, frame_count=4)
        out_dir = str(tmp_path / "frames")

        result = extract_frames(video_path, out_dir)
        for f in result.frames:
            assert f.path.endswith(".png")

    def test_keyframe_detection_reduces_count(self, tmp_path):
        from core.video_to_sprite.frame_extractor import extract_frames

        video_path = str(tmp_path / "test.mp4")
        # Create video with mostly static frames + 1 big change
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(str(video_path), fourcc, 12.0, (64, 64))
        for i in range(10):
            frame = np.ones((64, 64, 3), dtype=np.uint8) * 50  # static
            out_writer.write(frame)
        # 1 very different frame
        frame = np.ones((64, 64, 3), dtype=np.uint8) * 200
        out_writer.write(frame)
        for i in range(5):
            frame = np.ones((64, 64, 3), dtype=np.uint8) * 200  # static again
            out_writer.write(frame)
        out_writer.release()

        out_dir = str(tmp_path / "frames")
        result_all = extract_frames(str(video_path), out_dir + "_all", keyframes_only=False)
        result_kf = extract_frames(str(video_path), out_dir + "_kf", keyframes_only=True, scene_threshold=25.0)

        assert result_kf.success
        assert len(result_kf.frames) < len(result_all.frames)
