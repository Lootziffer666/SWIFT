"""Visualisiere Skelette überlagert auf Original-Frames."""

import json
from pathlib import Path
from typing import List

import cv2
import numpy as np
from PIL import Image, ImageDraw


def visualize_skeleton_on_frame(
    frame_image: np.ndarray,
    skeleton_data: dict,
    frame_idx: int,
    bone_color: tuple = (0, 255, 0),  # Grün
    joint_color: tuple = (255, 0, 0),  # Rot
    thickness: int = 2,
) -> np.ndarray:
    """
    Überlagere Skelett auf Original-Frame.

    Args:
        frame_image: Original-Bild (BGR)
        skeleton_data: Dict aus skeleton_data.json
        frame_idx: Welcher Frame (0-basiert)
        bone_color: RGB für Knochen
        joint_color: RGB für Gelenke
        thickness: Liniendicke

    Returns:
        Bild mit überlagertems Skelett
    """
    frame_data = skeleton_data["frames"][frame_idx]
    joints = frame_data["joints"]
    connections = skeleton_data["connections"]

    height, width = frame_image.shape[:2]
    output = frame_image.copy()

    # Zeichne Knochen (Connections)
    for bone_idx1, bone_idx2 in connections:
        joint_names = skeleton_data["joint_names"]
        if bone_idx1 < len(joint_names) and bone_idx2 < len(joint_names):
            j1_name = joint_names[bone_idx1]
            j2_name = joint_names[bone_idx2]

            if j1_name in joints and j2_name in joints:
                x1, y1, conf1 = joints[j1_name]
                x2, y2, conf2 = joints[j2_name]

                # Nur zeichnen wenn confidence hoch genug
                if conf1 > 0.3 and conf2 > 0.3:
                    pt1 = (int(x1 * width), int(y1 * height))
                    pt2 = (int(x2 * width), int(y2 * height))
                    cv2.line(output, pt1, pt2, bone_color, thickness)

    # Zeichne Gelenke
    for joint_name, (x, y, conf) in joints.items():
        if conf > 0.3:
            pt = (int(x * width), int(y * height))
            cv2.circle(output, pt, 5, joint_color, -1)
            # Confidence als Text
            cv2.putText(
                output,
                f"{conf:.2f}",
                (pt[0] + 8, pt[1]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                (255, 255, 255),
                1,
            )

    return output


def create_comparison_grid(
    original_frame: np.ndarray,
    skeleton_overlay: np.ndarray,
    stick_figure: np.ndarray,
) -> np.ndarray:
    """Erstelle 3-spaltige Vergleich-Grid: Original | Skeleton Overlay | Stick Figure."""
    # Resize alle auf gleiche Größe
    h, w = 300, 400
    original = cv2.resize(original_frame, (w, h))
    overlay = cv2.resize(skeleton_overlay, (w, h))
    stick = cv2.resize(stick_figure, (w, h))

    # Konvertiere Stick Figure von RGB zu BGR falls nötig
    if len(stick.shape) == 3 and stick.shape[2] == 3:
        # Assume PIL Image in RGB, convert to BGR for OpenCV
        stick = cv2.cvtColor(stick.astype(np.uint8), cv2.COLOR_RGB2BGR)

    # Erstelle Labels
    labels = ["ORIGINAL FRAME", "SKELETON OVERLAY", "STICK FIGURE"]
    for i, (img, label) in enumerate([(original, labels[0]), (overlay, labels[1]), (stick, labels[2])]):
        cv2.putText(
            img,
            label,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0) if i == 0 else (255, 0, 0) if i == 1 else (100, 100, 255),
            2,
        )

    # Stack horizontal
    grid = np.hstack([original, overlay, stick])
    return grid


def visualize_gif_sequence(
    gif_path: str,
    skeleton_json: str,
    output_dir: str,
    frames_to_show: List[int] = None,
) -> None:
    """
    Erstelle Vergleichsgridss für mehrere Frames.

    Args:
        gif_path: Pfad zum GIF
        skeleton_json: Pfad zu skeleton_data.json
        output_dir: Wo Ausgabe speichern
        frames_to_show: Welche Frame-Indices anzeigen (default: 0, 100, 200, ...)
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)

    # Lade Skeleton-Daten
    with open(skeleton_json) as f:
        skeleton_data = json.load(f)

    # Öffne GIF
    from PIL import Image as PILImage
    gif = PILImage.open(gif_path)
    width, height = gif.size

    # Default Frames
    if frames_to_show is None:
        total_frames = len(skeleton_data["frames"])
        frames_to_show = list(range(0, total_frames, max(1, total_frames // 5)))[:5]

    # Verarbeite Frames
    for frame_idx in frames_to_show:
        # Lade GIF Frame
        gif.seek(frame_idx)
        original_frame = cv2.cvtColor(
            np.array(gif.convert("RGB")), cv2.COLOR_RGB2BGR
        )

        # Erstelle Overlay
        skeleton_overlay = visualize_skeleton_on_frame(
            original_frame, skeleton_data, frame_idx
        )

        # Lade Stick Figure
        stick_figure_path = (
            Path(skeleton_json).parent
            / "stick_figures"
            / f"stick_{frame_idx:04d}.png"
        )
        if stick_figure_path.exists():
            stick_figure = cv2.imread(str(stick_figure_path))
        else:
            stick_figure = np.zeros_like(original_frame)

        # Erstelle Grid
        grid = create_comparison_grid(original_frame, skeleton_overlay, stick_figure)

        # Speichere
        output_file = output_path / f"comparison_{frame_idx:04d}.png"
        cv2.imwrite(str(output_file), grid)
        print(f"✓ {output_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("gif", help="GIF-Datei")
    parser.add_argument("skeleton_json", help="skeleton_data.json")
    parser.add_argument("-o", "--output", default="skeleton_comparisons")
    parser.add_argument(
        "--frames",
        type=int,
        nargs="+",
        help="Welche Frame-Indices anzeigen",
    )

    args = parser.parse_args()
    visualize_gif_sequence(args.gif, args.skeleton_json, args.output, args.frames)
