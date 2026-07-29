"""Visualisiere Körperteile mit Bewegungs-Vektoren."""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from motion_tracker import MotionTracker, LIMB_DEFINITIONS


def draw_limb_sequence(
    output_path: str,
    skeleton_json: str,
    frame_range: tuple,
    limb_types: list = None,
):
    """
    Zeichne Körperteile mit Bewegungs-Vektoren für mehrere Frames.

    Args:
        output_path: Ausgabe-PNG
        skeleton_json: skeleton_data.json
        frame_range: (start_frame, end_frame)
        limb_types: Welche Körperteile zeichnen (default: alle)
    """
    with open(skeleton_json) as f:
        data = json.load(f)

    tracker = MotionTracker(skeleton_json)

    # Standard Größe
    width, height = 1200, 400

    # Erstelle Bilder pro Frame
    start_frame, end_frame = frame_range
    frame_images = []

    for frame_data in data["frames"]:
        frame_idx = frame_data["frame"]
        if not (start_frame <= frame_idx <= end_frame):
            continue

        # Leeres Bild
        img = Image.new("RGB", (width, height), (240, 240, 240))
        draw = ImageDraw.Draw(img)

        # Zeichne Mittellinie
        draw.line([(0, height // 2), (width, height // 2)], fill=(200, 200, 200), width=1)

        # Zeichne Körperteile
        joints = frame_data.get("joints", {})

        for limb_def in LIMB_DEFINITIONS:
            if limb_types and limb_def.name not in limb_types:
                continue

            # Zeichne Limb-Segmente (Knochen)
            for i in range(len(limb_def.joint_sequence) - 1):
                j1_name = limb_def.joint_sequence[i]
                j2_name = limb_def.joint_sequence[i + 1]

                if j1_name in joints and j2_name in joints:
                    x1, y1, c1 = joints[j1_name]
                    x2, y2, c2 = joints[j2_name]

                    if c1 > 0.3 and c2 > 0.3:
                        px1 = int(x1 * width)
                        py1 = int(y1 * height)
                        px2 = int(x2 * width)
                        py2 = int(y2 * height)

                        draw.line(
                            [(px1, py1), (px2, py2)],
                            fill=limb_def.color,
                            width=4,
                        )

            # Zeichne Gelenke
            for j_name in limb_def.joint_sequence:
                if j_name in joints:
                    x, y, conf = joints[j_name]
                    if conf > 0.3:
                        px = int(x * width)
                        py = int(y * height)
                        r = 6
                        draw.ellipse(
                            [(px - r, py - r), (px + r, py + r)],
                            fill=limb_def.color,
                        )

        # Frame-Label
        draw.text(
            (10, 10),
            f"Frame {frame_idx}",
            fill=(0, 0, 0),
        )

        frame_images.append(img)

    if frame_images:
        # Stack horizontal
        combined_width = width * len(frame_images)
        combined = Image.new("RGB", (combined_width, height), (255, 255, 255))

        for i, img in enumerate(frame_images):
            combined.paste(img, (i * width, 0))

        combined.save(output_path)
        print(f"✓ Saved: {output_path}")
        return combined

    return None


def draw_joint_trajectory(
    output_path: str,
    skeleton_json: str,
    joint_name: str,
    frame_range: tuple = None,
):
    """
    Zeichne die Trajektorie eines einzelnen Joints über mehrere Frames.
    """
    with open(skeleton_json) as f:
        data = json.load(f)

    tracker = MotionTracker(skeleton_json)

    if joint_name not in tracker.joint_tracks:
        print(f"Joint {joint_name} not found")
        return

    track = tracker.joint_tracks[joint_name]
    limb = tracker.find_limb_by_joint(joint_name)

    # Canvas
    width, height = 600, 600
    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    # Zeichne Grid
    for x in range(0, width, 50):
        draw.line([(x, 0), (x, height)], fill=(230, 230, 230), width=1)
    for y in range(0, height, 50):
        draw.line([(0, y), (width, y)], fill=(230, 230, 230), width=1)

    # Bestimme Frame-Range
    if frame_range is None:
        start_idx, end_idx = 0, len(track.positions)
    else:
        start_frame, end_frame = frame_range
        start_idx = next(
            (i for i, f in enumerate(track.frame_indices) if f >= start_frame), 0
        )
        end_idx = next(
            (i for i, f in enumerate(track.frame_indices) if f > end_frame),
            len(track.positions),
        )

    positions = track.positions[start_idx:end_idx]
    frames = track.frame_indices[start_idx:end_idx]
    confidences = track.confidences[start_idx:end_idx]

    # Zeichne Trajektorie
    color = tuple(limb.color) if limb else (100, 100, 100)

    # Punkte
    for i, (x, y) in enumerate(positions):
        px = int(x * width)
        py = int(y * height)

        # Farbe basierend auf Confidence
        conf = confidences[i]
        brightness = int(100 + conf * 155)  # 100-255
        pt_color = (brightness, brightness, brightness)

        draw.ellipse(
            [(px - 4, py - 4), (px + 4, py + 4)],
            fill=color,
        )

    # Linien zwischen Punkten
    for i in range(1, len(positions)):
        x1, y1 = positions[i - 1]
        x2, y2 = positions[i]
        px1, py1 = int(x1 * width), int(y1 * height)
        px2, py2 = int(x2 * width), int(y2 * height)

        # Alpha-Blending für Gradient
        alpha = (i / len(positions)) * 0.8
        draw.line([(px1, py1), (px2, py2)], fill=color, width=1)

    # Labels
    draw.text((10, 10), f"Joint Trajectory: {joint_name}", fill=(0, 0, 0))
    draw.text((10, 30), f"Limb: {limb.name if limb else 'Unknown'}", fill=(0, 0, 0))
    draw.text(
        (10, 50),
        f"Frames: {frames[0] if frames else '?'} - {frames[-1] if frames else '?'}",
        fill=(0, 0, 0),
    )
    draw.text(
        (10, 70),
        f"Total Distance: {track.get_distance_traveled():.2f}px",
        fill=(0, 0, 0),
    )

    img.save(output_path)
    print(f"✓ Saved: {output_path}")
    return img


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("skeleton_json", help="skeleton_data.json")
    parser.add_argument(
        "--limb-sequence",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Draw limb sequence (start_frame end_frame)",
    )
    parser.add_argument(
        "--joint-trajectory",
        help="Draw joint trajectory",
    )
    parser.add_argument("-o", "--output", default="output.png")

    args = parser.parse_args()

    if args.limb_sequence:
        draw_limb_sequence(args.output, args.skeleton_json, tuple(args.limb_sequence))
    elif args.joint_trajectory:
        draw_joint_trajectory(args.output, args.skeleton_json, args.joint_trajectory)
