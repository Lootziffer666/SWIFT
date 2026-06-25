"""
Video motion capture using MediaPipe Pose.
Extracts 3D joint landmarks per frame and returns them as structured data.
"""
import os
from dataclasses import dataclass
from typing import Optional, Callable

import cv2
import numpy as np

try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False


# MediaPipe landmark indices mapped to human-readable names
LANDMARK_NAMES = {
    0:  "nose",
    11: "left_shoulder",  12: "right_shoulder",
    13: "left_elbow",     14: "right_elbow",
    15: "left_wrist",     16: "right_wrist",
    23: "left_hip",       24: "right_hip",
    25: "left_knee",      26: "right_knee",
    27: "left_ankle",     28: "right_ankle",
}


@dataclass
class Joint:
    name: str
    x: float
    y: float
    z: float
    visibility: float


@dataclass
class PoseFrame:
    frame_index: int
    timestamp_ms: float
    joints: dict  # name → Joint


@dataclass
class TrackingResult:
    success: bool
    frames: list
    fps: float
    total_frames: int
    error: Optional[str] = None


class VideoTracker:
    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5):
        if not MP_AVAILABLE:
            raise ImportError("mediapipe is required. Install with: pip install mediapipe")
        self._det_conf = min_detection_confidence
        self._track_conf = min_tracking_confidence

    def track(
        self,
        video_path: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> TrackingResult:
        if not os.path.isfile(video_path):
            return TrackingResult(success=False, frames=[], fps=0, total_frames=0,
                                  error=f"File not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return TrackingResult(success=False, frames=[], fps=0, total_frames=0,
                                  error="Cannot open video file")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        mp_pose = mp.solutions.pose
        pose_results = []

        with mp_pose.Pose(
            min_detection_confidence=self._det_conf,
            min_tracking_confidence=self._track_conf,
            model_complexity=1,
        ) as pose:
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb)
                timestamp_ms = (frame_idx / fps) * 1000.0

                joints = {}
                if result.pose_world_landmarks:
                    for idx, name in LANDMARK_NAMES.items():
                        lm = result.pose_world_landmarks.landmark[idx]
                        joints[name] = Joint(
                            name=name,
                            x=lm.x, y=lm.y, z=lm.z,
                            visibility=lm.visibility,
                        )

                pose_results.append(PoseFrame(
                    frame_index=frame_idx,
                    timestamp_ms=timestamp_ms,
                    joints=joints,
                ))

                if progress_cb:
                    progress_cb(frame_idx, total)
                frame_idx += 1

        cap.release()
        return TrackingResult(
            success=True,
            frames=pose_results,
            fps=fps,
            total_frames=frame_idx,
        )
