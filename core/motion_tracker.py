"""
Motion Tracking: Verfolge Gelenke über mehrere Frames und segmentiere Körperteile.

Weiterentwicklung der Skeleton Detection:
- Temporale Kohärenz (Joint-Tracking über Frames)
- Körperteil-Identifikation (Arm, Bein, Kopf, Torso)
- Bewegungsanalyse pro Gliedmaße
- Validierung von anatomischen Constraints
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial.distance import euclidean


class LimbType(Enum):
    """Körperteile-Klassifikation."""
    HEAD = "head"
    TORSO = "torso"
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_LEG = "left_leg"
    RIGHT_LEG = "right_leg"


@dataclass
class LimbDefinition:
    """Definition eines Körperteils als Sequenz von Joints."""
    name: str
    limb_type: LimbType
    joint_sequence: List[str]  # z.B. ["left_shoulder", "left_elbow", "left_wrist"]
    color: Tuple[int, int, int]  # RGB für Visualisierung

    def get_segments(self) -> List[Tuple[str, str]]:
        """Gib Bone-Segmente (Joint-Paare) zurück."""
        return [(self.joint_sequence[i], self.joint_sequence[i + 1])
                for i in range(len(self.joint_sequence) - 1)]


# Anatomische Körperteil-Definitionen
LIMB_DEFINITIONS = [
    LimbDefinition(
        "Head", LimbType.HEAD,
        ["nose", "left_eye", "right_eye", "left_ear", "right_ear"],
        (255, 100, 100)  # Rot
    ),
    LimbDefinition(
        "Torso", LimbType.TORSO,
        ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
        (100, 255, 100)  # Grün
    ),
    LimbDefinition(
        "Left Arm", LimbType.LEFT_ARM,
        ["left_shoulder", "left_elbow", "left_wrist"],
        (100, 100, 255)  # Blau
    ),
    LimbDefinition(
        "Right Arm", LimbType.RIGHT_ARM,
        ["right_shoulder", "right_elbow", "right_wrist"],
        (255, 255, 100)  # Gelb
    ),
    LimbDefinition(
        "Left Leg", LimbType.LEFT_LEG,
        ["left_hip", "left_knee", "left_ankle"],
        (255, 100, 255)  # Magenta
    ),
    LimbDefinition(
        "Right Leg", LimbType.RIGHT_LEG,
        ["right_hip", "right_knee", "right_ankle"],
        (100, 255, 255)  # Cyan
    ),
]


@dataclass
class JointTrack:
    """Verfolge einen einzelnen Joint über Frames."""
    joint_name: str
    positions: List[Tuple[float, float]]  # [(x, y), ...] über Frames
    confidences: List[float]
    frame_indices: List[int]

    def get_velocity(self, frame_idx: int, window: int = 3) -> Tuple[float, float]:
        """Berechne Geschwindigkeit (pixel/frame)."""
        if len(self.positions) < 2:
            return (0.0, 0.0)

        # Finde Position im Track
        try:
            local_idx = self.frame_indices.index(frame_idx)
        except ValueError:
            return (0.0, 0.0)

        if local_idx == 0:
            return (0.0, 0.0)

        start_idx = max(0, local_idx - window)
        x1, y1 = self.positions[start_idx]
        x2, y2 = self.positions[local_idx]
        frame_delta = self.frame_indices[local_idx] - self.frame_indices[start_idx]

        if frame_delta == 0:
            return (0.0, 0.0)

        return ((x2 - x1) / frame_delta, (y2 - y1) / frame_delta)

    def get_distance_traveled(self) -> float:
        """Berechne Gesamtdistanz über alle Frames."""
        total = 0.0
        for i in range(1, len(self.positions)):
            x1, y1 = self.positions[i - 1]
            x2, y2 = self.positions[i]
            total += euclidean((x1, y1), (x2, y2))
        return total

    def get_confidence_average(self) -> float:
        """Durchschnittliche Confidence."""
        if not self.confidences:
            return 0.0
        return sum(self.confidences) / len(self.confidences)

    def is_visible(self, threshold: float = 0.3) -> bool:
        """Ist dieser Joint überhaupt sichtbar?"""
        return self.get_confidence_average() > threshold


@dataclass
class LimbTrack:
    """Verfolge ein ganzes Körperteil über Frames."""
    limb_def: LimbDefinition
    joint_tracks: Dict[str, JointTrack] = field(default_factory=dict)
    frame_count: int = 0

    def add_joint_track(self, joint_track: JointTrack):
        """Füge Joint-Track für diesen Limb hinzu."""
        if joint_track.joint_name in self.limb_def.joint_sequence:
            self.joint_tracks[joint_track.joint_name] = joint_track
            self.frame_count = max(self.frame_count, len(joint_track.positions))

    def is_complete(self) -> bool:
        """Hat dieser Limb alle seine Joints?"""
        return len(self.joint_tracks) == len(self.limb_def.joint_sequence)

    def is_visible(self, threshold: float = 0.3) -> bool:
        """Ist dieser Limb (insgesamt) sichtbar?"""
        visible_count = sum(
            1 for jt in self.joint_tracks.values() if jt.is_visible(threshold)
        )
        return visible_count >= len(self.limb_def.joint_sequence) * 0.7  # 70% Threshold

    def get_total_movement(self) -> float:
        """Wie viel hat dieser Limb sich insgesamt bewegt?"""
        return sum(jt.get_distance_traveled() for jt in self.joint_tracks.values())

    def get_limb_length(self, frame_idx: int) -> Optional[float]:
        """Berechne Länge des Limbs in einem Frame (z.B. Armlänge)."""
        joints_in_frame = []

        for joint_name in self.limb_def.joint_sequence:
            if joint_name in self.joint_tracks:
                track = self.joint_tracks[joint_name]
                try:
                    local_idx = track.frame_indices.index(frame_idx)
                    joints_in_frame.append(track.positions[local_idx])
                except ValueError:
                    pass

        if len(joints_in_frame) < 2:
            return None

        # Berechne Gesamtlänge der Kette
        total_length = 0.0
        for i in range(len(joints_in_frame) - 1):
            total_length += euclidean(joints_in_frame[i], joints_in_frame[i + 1])

        return total_length


class MotionTracker:
    """Verfolge Motion über mehrere Frames mit Körperteil-Segmentation."""

    def __init__(self, skeleton_json: str):
        """Lade Skeleton-Daten und initialisiere Tracking."""
        with open(skeleton_json) as f:
            self.data = json.load(f)

        self.joint_names = self.data["joint_names"]
        self.joint_tracks: Dict[str, JointTrack] = {}
        self.limb_tracks: Dict[str, LimbTrack] = {}

        self._build_tracks()

    def _build_tracks(self):
        """Baue Joint- und Limb-Tracks aus Skeleton-Daten."""
        # Erstelle Joint-Tracks
        for joint_name in self.joint_names:
            positions = []
            confidences = []
            frame_indices = []

            for frame_data in self.data["frames"]:
                if joint_name in frame_data.get("joints", {}):
                    x, y, conf = frame_data["joints"][joint_name]
                    positions.append((x, y))
                    confidences.append(conf)
                    frame_indices.append(frame_data["frame"])

            if positions:
                self.joint_tracks[joint_name] = JointTrack(
                    joint_name, positions, confidences, frame_indices
                )

        # Erstelle Limb-Tracks
        for limb_def in LIMB_DEFINITIONS:
            limb_track = LimbTrack(limb_def)

            for joint_name in limb_def.joint_sequence:
                if joint_name in self.joint_tracks:
                    limb_track.add_joint_track(self.joint_tracks[joint_name])

            self.limb_tracks[limb_def.name] = limb_track

    def get_limb_summary(self) -> str:
        """Gib Zusammenfassung aller Körperteile."""
        summary = []
        summary.append("=" * 70)
        summary.append("KÖRPERTEIL-ANALYSE (Motion Tracking)")
        summary.append("=" * 70)

        for limb_name, limb_track in self.limb_tracks.items():
            limb_def = limb_track.limb_def
            visible = limb_track.is_visible()
            complete = limb_track.is_complete()
            total_move = limb_track.get_total_movement()

            status = "✓ SICHTBAR" if visible else "✗ NICHT SICHTBAR"
            complete_status = "✓" if complete else "✗"

            summary.append(f"\n{limb_name} ({limb_def.limb_type.value})")
            summary.append(f"  Status: {status}")
            summary.append(f"  Vollständig: {complete_status} ({len(limb_track.joint_tracks)}/{len(limb_def.joint_sequence)} Joints)")
            summary.append(f"  Bewegung: {total_move:.2f} Pixel (über {limb_track.frame_count} Frames)")

            # Pro Joint
            for joint_name in limb_def.joint_sequence:
                if joint_name in limb_track.joint_tracks:
                    jt = limb_track.joint_tracks[joint_name]
                    dist = jt.get_distance_traveled()
                    conf = jt.get_confidence_average()
                    vx, vy = jt.get_velocity(self.data["frames"][-1]["frame"])
                    vel = np.sqrt(vx**2 + vy**2)

                    summary.append(
                        f"    • {joint_name:20} Dist={dist:8.2f}px  "
                        f"Conf={conf:5.1%}  Vel={vel:6.2f}px/f"
                    )

        return "\n".join(summary)

    def find_most_moving_limb(self) -> Optional[Tuple[str, float]]:
        """Welcher Limb bewegt sich am meisten?"""
        max_limb = None
        max_movement = 0.0

        for limb_name, limb_track in self.limb_tracks.items():
            if limb_track.is_visible():
                movement = limb_track.get_total_movement()
                if movement > max_movement:
                    max_movement = movement
                    max_limb = limb_name

        if max_limb:
            return (max_limb, max_movement)
        return None

    def find_limb_by_joint(self, joint_name: str) -> Optional[LimbDefinition]:
        """Zu welchem Körperteil gehört ein Joint?"""
        for limb_track in self.limb_tracks.values():
            if joint_name in limb_track.limb_def.joint_sequence:
                return limb_track.limb_def
        return None

    def validate_anatomical_consistency(self) -> List[str]:
        """Prüfe auf anatomische Unstimmigkeiten."""
        issues = []

        # Prüfe Arm-Länge (sollte konstant sein)
        for arm_name in ["Left Arm", "Right Arm"]:
            if arm_name in self.limb_tracks:
                limb = self.limb_tracks[arm_name]
                lengths = []

                for frame_data in self.data["frames"]:
                    length = limb.get_limb_length(frame_data["frame"])
                    if length:
                        lengths.append(length)

                if lengths:
                    avg_length = np.mean(lengths)
                    std_length = np.std(lengths)
                    # Wenn Standardabweichung > 30% vom Mittel: Problem!
                    if std_length > avg_length * 0.3:
                        issues.append(
                            f"{arm_name}: Länge variiert zu stark "
                            f"({avg_length:.1f}±{std_length:.1f}px)"
                        )

        # Prüfe Schulter-Abstand (sollte konstant sein)
        if "left_shoulder" in self.joint_tracks and "right_shoulder" in self.joint_tracks:
            ls_track = self.joint_tracks["left_shoulder"]
            rs_track = self.joint_tracks["right_shoulder"]

            distances = []
            for i in range(min(len(ls_track.positions), len(rs_track.positions))):
                dist = euclidean(ls_track.positions[i], rs_track.positions[i])
                distances.append(dist)

            if distances:
                avg_dist = np.mean(distances)
                std_dist = np.std(distances)
                if std_dist > avg_dist * 0.4:
                    issues.append(
                        f"Schulter-Distanz variiert: {avg_dist:.1f}±{std_dist:.1f}px"
                    )

        return issues

    def export_tracking_report(self, output_file: str):
        """Exportiere kompletten Tracking-Report."""
        with open(output_file, "w") as f:
            f.write(self.get_limb_summary())
            f.write("\n\n")

            f.write("=" * 70)
            f.write("\nANATOMISCHE VALIDIERUNG\n")
            f.write("=" * 70)
            f.write("\n")

            issues = self.validate_anatomical_consistency()
            if issues:
                for issue in issues:
                    f.write(f"⚠️  {issue}\n")
            else:
                f.write("✓ Keine Unstimmigkeiten gefunden\n")

            f.write("\n" + "=" * 70)
            f.write("\nBEWEGUNGS-HIGHLIGHTS\n")
            f.write("=" * 70)
            f.write("\n")

            most_moving = self.find_most_moving_limb()
            if most_moving:
                limb_name, movement = most_moving
                f.write(f"🏃 Aktivster Limb: {limb_name} ({movement:.1f}px Bewegung)\n")
