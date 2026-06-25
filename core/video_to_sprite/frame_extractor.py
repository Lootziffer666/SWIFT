"""
Extract frames from video files.
Supports all-frames extraction and keyframe detection (scene change based).
"""
import os
from dataclasses import dataclass
from typing import Optional, Callable

import cv2
import numpy as np


@dataclass
class ExtractedFrame:
    index: int
    timestamp_ms: float
    path: str
    is_keyframe: bool = False


@dataclass
class ExtractionResult:
    success: bool
    frames: list
    fps: float
    source_path: str
    out_dir: str
    error: Optional[str] = None


def _scene_change_score(prev_gray, curr_gray) -> float:
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(np.mean(diff))


def extract_frames(
    video_path: str,
    out_dir: str,
    keyframes_only: bool = False,
    scene_threshold: float = 25.0,
    max_frames: Optional[int] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> ExtractionResult:
    if not os.path.isfile(video_path):
        return ExtractionResult(
            success=False, frames=[], fps=0,
            source_path=video_path, out_dir=out_dir,
            error=f"File not found: {video_path}"
        )

    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return ExtractionResult(
            success=False, frames=[], fps=0,
            source_path=video_path, out_dir=out_dir,
            error="Cannot open video"
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    frames = []
    prev_gray = None
    frame_idx = 0
    saved_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if max_frames and saved_idx >= max_frames:
            break

        timestamp_ms = (frame_idx / fps) * 1000.0
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        is_keyframe = False
        if keyframes_only:
            if prev_gray is None:
                is_keyframe = True
            else:
                score = _scene_change_score(prev_gray, curr_gray)
                is_keyframe = score > scene_threshold
        else:
            is_keyframe = True  # all frames are "key" in full mode

        if is_keyframe:
            out_name = f"frame_{saved_idx:04d}.png"
            out_path = os.path.join(out_dir, out_name)
            cv2.imwrite(out_path, frame)
            frames.append(ExtractedFrame(
                index=saved_idx,
                timestamp_ms=timestamp_ms,
                path=out_path,
                is_keyframe=keyframes_only,
            ))
            saved_idx += 1

        prev_gray = curr_gray
        if progress_cb:
            progress_cb(frame_idx, total)
        frame_idx += 1

    cap.release()
    return ExtractionResult(
        success=True,
        frames=frames,
        fps=fps,
        source_path=video_path,
        out_dir=out_dir,
    )
