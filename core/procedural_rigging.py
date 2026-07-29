"""
Procedural Rigging System: Maps Skelett-Daten zu Kampf-Aktionen.

Verbindet erkannte Motion-Capture Daten mit Kampfmechaniken:
- Skeleton Frames → Combat Poses
- Combat State → Animierte Pose Interpolation
- Different Rendering Styles (Stick, Sketch, Cartoon, etc.)
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw


class RenderStyle(Enum):
    """Rendering-Stile für das gleiche Skelett."""
    STICK = "stick"           # Nur Linien (aktuell)
    SKETCH = "sketch"         # Grobe Zeichnungen
    CARTOON = "cartoon"       # Animationsstil
    REALISTIC = "realistic"   # Motion-Capture Quality


@dataclass
class PoseFrame:
    """Ein Frame mit Pose-Daten (Position, Rotation pro Joint)."""
    frame_id: int
    joints: Dict[str, Tuple[float, float]]  # {joint_name: (x, y)}
    metadata: dict = None

    def interpolate_to(self, other: "PoseFrame", t: float) -> "PoseFrame":
        """Interpoliere zwischen zwei Poses (t: 0-1)."""
        interpolated = PoseFrame(self.frame_id, {})

        all_joints = set(self.joints.keys()) | set(other.joints.keys())
        for joint_name in all_joints:
            if joint_name in self.joints and joint_name in other.joints:
                x1, y1 = self.joints[joint_name]
                x2, y2 = other.joints[joint_name]
                x = x1 * (1 - t) + x2 * t
                y = y1 * (1 - t) + y2 * t
                interpolated.joints[joint_name] = (x, y)
            elif joint_name in self.joints:
                interpolated.joints[joint_name] = self.joints[joint_name]
            else:
                interpolated.joints[joint_name] = other.joints[joint_name]

        return interpolated


class ProceduralRig:
    """
    Prozedurales Rigging: Maps Skelett zu verschiedenen Representations.

    Nutzung:
        rig = ProceduralRig("skeleton_data.json")
        attack_pose = rig.pose_for_action("attack", facing_right=True)
        rig.render_pose(attack_pose, output_file="attack.png")
    """

    def __init__(self, skeleton_json: str):
        """Lade Skelett-Daten."""
        with open(skeleton_json) as f:
            self.data = json.load(f)

        self.frames: List[PoseFrame] = []
        self._load_frames()

        # Motion-Analyse
        self.motion_intensity = self._calculate_motion_intensity()

    def _load_frames(self):
        """Konvertiere JSON-Frames zu PoseFrame-Objekten."""
        for frame_data in self.data.get("frames", []):
            pose_frame = PoseFrame(
                frame_id=frame_data["frame"],
                joints=self._normalize_joints(frame_data.get("joints", {})),
            )
            self.frames.append(pose_frame)

    def _normalize_joints(self, joints: dict) -> Dict[str, Tuple[float, float]]:
        """Normalisiere Joint-Koordinaten (nur x, y)."""
        normalized = {}
        for joint_name, (x, y, *_) in joints.items():
            normalized[joint_name] = (x, y)
        return normalized

    def _calculate_motion_intensity(self) -> float:
        """Berechne durchschnittliche Bewegungsintensität."""
        if len(self.frames) < 2:
            return 0.0

        total_motion = 0.0
        for i in range(len(self.frames) - 1):
            for joint_name in self.frames[i].joints:
                if joint_name in self.frames[i + 1].joints:
                    x1, y1 = self.frames[i].joints[joint_name]
                    x2, y2 = self.frames[i + 1].joints[joint_name]
                    distance = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    total_motion += distance

        return total_motion / (len(self.frames) - 1)

    def pose_for_action(
        self,
        action: str,
        facing_right: bool = True,
        intensity: float = 1.0,
    ) -> PoseFrame:
        """
        Generiere Pose für eine Kampf-Aktion.

        Args:
            action: "attack", "defend", "dodge", "wait"
            facing_right: Blickrichtung des Kämpfers
            intensity: Intensität der Aktion (0-1)

        Returns:
            PoseFrame passend zur Aktion
        """
        if not self.frames:
            raise ValueError("Keine Frames geladen")

        # Wähle Frames basierend auf Action
        frame_ranges = {
            "attack": (0.0, 0.33),      # Erstes Drittel
            "defend": (0.33, 0.66),     # Mittleres Drittel
            "dodge": (0.66, 1.0),       # Letztes Drittel
            "wait": (0.5, 0.5),         # Mitte
        }

        if action not in frame_ranges:
            action = "wait"

        start_ratio, end_ratio = frame_ranges[action]
        start_idx = int(start_ratio * len(self.frames))
        end_idx = int(end_ratio * len(self.frames))
        end_idx = max(end_idx, start_idx + 1)

        # Wähle Frame basierend auf Intensität
        frame_idx = start_idx + int((end_idx - start_idx) * intensity)
        frame_idx = min(frame_idx, len(self.frames) - 1)

        selected_frame = self.frames[frame_idx]

        # Mirror wenn nötig
        if not facing_right:
            selected_frame = self._mirror_pose(selected_frame)

        return selected_frame

    def _mirror_pose(self, pose: PoseFrame) -> PoseFrame:
        """Spiegele Pose (linke ↔ rechte Seite)."""
        mirrored_joints = {}

        # Joint-Paare für Spiegelung
        mirror_pairs = {
            "left_eye": "right_eye",
            "left_ear": "right_ear",
            "left_shoulder": "right_shoulder",
            "left_elbow": "right_elbow",
            "left_wrist": "right_wrist",
            "left_hip": "right_hip",
            "left_knee": "right_knee",
            "left_ankle": "right_ankle",
        }

        for joint_name, (x, y) in pose.joints.items():
            # Spiegle X-Koordinate
            mirrored_x = 1.0 - x

            # Tausche Seite wenn möglich
            if joint_name in mirror_pairs:
                mirror_joint = mirror_pairs[joint_name]
                # Speichere unter dem gespiegelten Namen
                mirrored_joints[mirror_joint] = (mirrored_x, y)
            elif any(joint_name in mirror_pairs.values()):
                # Reverse lookup
                for key, val in mirror_pairs.items():
                    if val == joint_name:
                        mirrored_joints[key] = (mirrored_x, y)
                        break
            else:
                # Zentrale Joints (nose, neck, etc.)
                mirrored_joints[joint_name] = (mirrored_x, y)

        return PoseFrame(pose.frame_id, mirrored_joints)

    def render_pose(
        self,
        pose: PoseFrame,
        width: int = 256,
        height: int = 256,
        style: RenderStyle = RenderStyle.STICK,
    ) -> Image.Image:
        """Rendere eine Pose."""
        if style == RenderStyle.STICK:
            return self._render_stick(pose, width, height)
        elif style == RenderStyle.SKETCH:
            return self._render_sketch(pose, width, height)
        else:
            # Fallback to stick
            return self._render_stick(pose, width, height)

    def _render_stick(self, pose: PoseFrame, width: int, height: int) -> Image.Image:
        """Rendere Skeleton als Stick Figure."""
        img = Image.new("RGB", (width, height), (20, 20, 30))
        draw = ImageDraw.Draw(img)

        # Bones
        joint_names = list(self.data["joint_names"])
        connections = self.data["connections"]

        for j1_idx, j2_idx in connections:
            if j1_idx < len(joint_names) and j2_idx < len(joint_names):
                j1_name = joint_names[j1_idx]
                j2_name = joint_names[j2_idx]

                if j1_name in pose.joints and j2_name in pose.joints:
                    x1, y1 = pose.joints[j1_name]
                    x2, y2 = pose.joints[j2_name]

                    px1, py1 = int(x1 * width), int(y1 * height)
                    px2, py2 = int(x2 * width), int(y2 * height)

                    draw.line([(px1, py1), (px2, py2)], fill=(200, 200, 200), width=3)

        # Joints
        for joint_name, (x, y) in pose.joints.items():
            px, py = int(x * width), int(y * height)
            r = 4
            draw.ellipse(
                [(px - r, py - r), (px + r, py + r)], fill=(255, 100, 100)
            )

        return img

    def _render_sketch(self, pose: PoseFrame, width: int, height: int) -> Image.Image:
        """Rendere Pose als grobe Zeichnung (erweiterbar)."""
        # Für jetzt: wie Stick, aber mit dickeren Linien
        img = Image.new("RGB", (width, height), (240, 240, 240))
        draw = ImageDraw.Draw(img)

        joint_names = list(self.data["joint_names"])
        connections = self.data["connections"]

        for j1_idx, j2_idx in connections:
            if j1_idx < len(joint_names) and j2_idx < len(joint_names):
                j1_name = joint_names[j1_idx]
                j2_name = joint_names[j2_idx]

                if j1_name in pose.joints and j2_name in pose.joints:
                    x1, y1 = pose.joints[j1_name]
                    x2, y2 = pose.joints[j2_name]

                    px1, py1 = int(x1 * width), int(y1 * height)
                    px2, py2 = int(x2 * width), int(y2 * height)

                    # Dickere Linien für Sketch-Style
                    draw.line([(px1, py1), (px2, py2)], fill=(50, 50, 50), width=6)

        # Größere Joints
        for joint_name, (x, y) in pose.joints.items():
            px, py = int(x * width), int(y * height)
            r = 6
            draw.ellipse(
                [(px - r, py - r), (px + r, py + r)], fill=(100, 100, 100)
            )

        return img


class CombatAnimationCompiler:
    """Kompiliert Combat State zu Animation Frames."""

    def __init__(self, rig1: ProceduralRig, rig2: ProceduralRig):
        self.rig1 = rig1
        self.rig2 = rig2

    def compile_turn(
        self,
        fighter1_action: str,
        fighter2_action: str,
        frame_count: int = 12,
        width: int = 256,
        height: int = 256,
    ) -> List[Tuple[Image.Image, Image.Image]]:
        """
        Generiere Animation Frames für einen Turn.

        Returns:
            List von (fighter1_frame, fighter2_frame) Image-Paaren
        """
        frames = []

        for frame_idx in range(frame_count):
            intensity = frame_idx / frame_count

            # Generiere Poses
            pose1 = self.rig1.pose_for_action(fighter1_action, intensity=intensity)
            pose2 = self.rig2.pose_for_action(
                fighter2_action, facing_right=False, intensity=intensity
            )

            # Rendere
            img1 = self.rig1.render_pose(pose1, width, height)
            img2 = self.rig2.render_pose(pose2, width, height)

            frames.append((img1, img2))

        return frames
