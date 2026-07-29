"""
Skeleton Detection & Stick Figure Generation from GIFs/Videos.

Nutzt MediaPipe Pose für Skelett-Erkennung und generiert Stick Figures
aus erkannten Joint-Positionen.
"""

import json
from pathlib import Path
from typing import Optional, List, Tuple

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw


class SkeletonFrame:
    """Ein Frame mit erkannten Skelett-Daten."""

    JOINT_NAMES = [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle"
    ]

    # Verbindungen zwischen Joints (Bones)
    CONNECTIONS = [
        (0, 1), (0, 2), (1, 3), (2, 4),  # Head
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # Arms
        (5, 11), (6, 12), (11, 12),  # Torso
        (11, 13), (13, 15), (12, 14), (14, 16),  # Legs
    ]

    def __init__(self, frame_idx: int, width: int, height: int):
        self.frame_idx = frame_idx
        self.width = width
        self.height = height
        self.joints = {}  # {joint_name: (x, y, confidence)}
        self.visible_joints = set()

    def set_joint(self, joint_name: str, x: float, y: float, confidence: float):
        """Setze Joint-Position (normalized coords 0-1)."""
        self.joints[joint_name] = (x, y, confidence)
        if confidence > 0.3:
            self.visible_joints.add(joint_name)

    def get_joint_pixel(self, joint_name: str) -> Optional[Tuple[int, int]]:
        """Gib Joint-Position in Pixel-Koordinaten."""
        if joint_name not in self.joints:
            return None
        x, y, conf = self.joints[joint_name]
        if conf < 0.3:
            return None
        return (int(x * self.width), int(y * self.height))

    def to_dict(self) -> dict:
        """Serialisiere zu Dict für JSON."""
        return {
            "frame": self.frame_idx,
            "width": self.width,
            "height": self.height,
            "joints": self.joints,
            "visible_count": len(self.visible_joints),
        }


class SkeletonDetector:
    """Erkennt Skelette in GIFs/Videos via MediaPipe Pose."""

    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,  # 0=light, 1=full, 2=heavy
            smooth_landmarks=True,
        )

    def process_gif(self, gif_path: str) -> List[SkeletonFrame]:
        """Verarbeite GIF und extrahiere Skelette pro Frame."""
        gif_path = Path(gif_path)
        if not gif_path.exists():
            raise FileNotFoundError(f"GIF nicht gefunden: {gif_path}")

        # GIF öffnen
        gif = Image.open(gif_path)
        width, height = gif.size
        skeleton_frames = []

        # Iteriere durch Frames
        frame_idx = 0
        try:
            while True:
                frame = np.array(gif.convert("RGB"))
                skeleton_frame = self._detect_skeleton(frame, frame_idx, width, height)
                skeleton_frames.append(skeleton_frame)

                frame_idx += 1
                gif.seek(frame_idx)
        except EOFError:
            pass  # Ende des GIFs

        return skeleton_frames

    def _detect_skeleton(
        self, frame: np.ndarray, frame_idx: int, width: int, height: int
    ) -> SkeletonFrame:
        """Erkenne Skelett in einem einzelnen Frame."""
        skeleton_frame = SkeletonFrame(frame_idx, width, height)

        # MediaPipe Pose Detection
        results = self.pose.process(frame)

        if results.pose_landmarks:
            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                if idx < len(SkeletonFrame.JOINT_NAMES):
                    joint_name = SkeletonFrame.JOINT_NAMES[idx]
                    skeleton_frame.set_joint(
                        joint_name, landmark.x, landmark.y, landmark.visibility
                    )

        return skeleton_frame

    def close(self):
        """Cleanup."""
        self.pose.close()


class StickFigureRenderer:
    """Rendert Skelette als Stick Figures."""

    # Styling - mit besseren Kontrasten
    BONE_WIDTH = 4
    JOINT_RADIUS = 5
    BONE_COLOR = (50, 50, 50)          # Dunkelgrau
    JOINT_COLOR = (255, 50, 50)        # Rot
    HIGHLIGHT_COLOR = (100, 255, 100)
    BG_COLOR = (240, 240, 240)         # Heller Hintergrund!

    @staticmethod
    def render_stick_figure(
        skeleton_frame: SkeletonFrame,
        bg_color: Optional[Tuple[int, int, int]] = None,
    ) -> Image.Image:
        """Rendere Skeleton als Stick Figure."""
        if bg_color is None:
            bg_color = StickFigureRenderer.BG_COLOR

        # Erstelle Bild
        img = Image.new("RGB", (skeleton_frame.width, skeleton_frame.height), bg_color)
        draw = ImageDraw.Draw(img)

        # Zeichne Knochen (Connections)
        for joint1_idx, joint2_idx in SkeletonFrame.CONNECTIONS:
            if joint1_idx < len(SkeletonFrame.JOINT_NAMES) and joint2_idx < len(
                SkeletonFrame.JOINT_NAMES
            ):
                joint1_name = SkeletonFrame.JOINT_NAMES[joint1_idx]
                joint2_name = SkeletonFrame.JOINT_NAMES[joint2_idx]

                pos1 = skeleton_frame.get_joint_pixel(joint1_name)
                pos2 = skeleton_frame.get_joint_pixel(joint2_name)

                if pos1 and pos2:
                    draw.line(
                        [pos1, pos2],
                        fill=StickFigureRenderer.BONE_COLOR,
                        width=StickFigureRenderer.BONE_WIDTH,
                    )

        # Zeichne Gelenke
        for joint_name in skeleton_frame.visible_joints:
            pos = skeleton_frame.get_joint_pixel(joint_name)
            if pos:
                x, y = pos
                r = StickFigureRenderer.JOINT_RADIUS
                draw.ellipse(
                    [x - r, y - r, x + r, y + r],
                    fill=StickFigureRenderer.JOINT_COLOR,
                )

        return img

    @staticmethod
    def render_sequence(
        skeleton_frames: List[SkeletonFrame], output_dir: str
    ) -> List[str]:
        """Rendere Sequenz von Stick Figures als PNG-Frames."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        output_files = []
        for skeleton_frame in skeleton_frames:
            img = StickFigureRenderer.render_stick_figure(skeleton_frame)
            frame_file = output_path / f"stick_{skeleton_frame.frame_idx:04d}.png"
            img.save(frame_file)
            output_files.append(str(frame_file))

        return output_files


class SkeletonAnalyzer:
    """Analysiert Skelett-Sequenzen."""

    @staticmethod
    def analyze_motion(skeleton_frames: List[SkeletonFrame]) -> dict:
        """Analysiere Bewegungsmuster."""
        if not skeleton_frames:
            return {}

        analysis = {
            "frame_count": len(skeleton_frames),
            "visible_joints_per_frame": [],
            "joint_movement": {},
            "confidence_stats": {},
        }

        # Joint-Bewegung tracking
        prev_positions = {}

        for skeleton_frame in skeleton_frames:
            visible_count = len(skeleton_frame.visible_joints)
            analysis["visible_joints_per_frame"].append(visible_count)

            for joint_name, (x, y, conf) in skeleton_frame.joints.items():
                if joint_name not in analysis["joint_movement"]:
                    analysis["joint_movement"][joint_name] = {
                        "total_distance": 0,
                        "frame_count": 0,
                    }

                if joint_name in prev_positions and conf > 0.3:
                    prev_x, prev_y, prev_conf = prev_positions[joint_name]
                    if prev_conf > 0.3:
                        distance = np.sqrt((x - prev_x) ** 2 + (y - prev_y) ** 2)
                        analysis["joint_movement"][joint_name]["total_distance"] += distance
                        analysis["joint_movement"][joint_name]["frame_count"] += 1

                prev_positions[joint_name] = (x, y, conf)

        # Berechne durchschnittliche Bewegung
        for joint_name, data in analysis["joint_movement"].items():
            if data["frame_count"] > 0:
                avg_distance = data["total_distance"] / data["frame_count"]
                data["avg_distance_per_frame"] = avg_distance
            del data["frame_count"]

        return analysis

    @staticmethod
    def export_skeleton_data(skeleton_frames: List[SkeletonFrame], output_file: str):
        """Exportiere Skeleton-Daten als JSON."""
        data = {
            "version": "1.0",
            "frame_count": len(skeleton_frames),
            "joint_names": SkeletonFrame.JOINT_NAMES,
            "connections": SkeletonFrame.CONNECTIONS,
            "frames": [frame.to_dict() for frame in skeleton_frames],
        }

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def import_skeleton_data(json_file: str) -> List[SkeletonFrame]:
        """Lade Skeleton-Daten aus JSON."""
        with open(json_file) as f:
            data = json.load(f)

        skeleton_frames = []
        for frame_data in data["frames"]:
            frame = SkeletonFrame(
                frame_data["frame"], frame_data["width"], frame_data["height"]
            )
            for joint_name, (x, y, conf) in frame_data["joints"].items():
                frame.set_joint(joint_name, x, y, conf)
            skeleton_frames.append(frame)

        return skeleton_frames
