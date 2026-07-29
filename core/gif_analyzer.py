"""CLI Tool zur Analyse von Kampf-GIFs und Skeleton-Extraktion."""

import argparse
import json
from pathlib import Path

from skeleton_detector import SkeletonDetector, StickFigureRenderer, SkeletonAnalyzer


def analyze_gif(gif_path: str, output_dir: str) -> dict:
    """
    Analysiere GIF und extrahiere Skeleton/Stick Figures.

    Returns:
        dict mit Metadaten und Ausgabepfaden
    """
    gif_path = Path(gif_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    print(f"📹 Analysiere GIF: {gif_path}")

    # Skeleton Detection
    detector = SkeletonDetector()
    skeleton_frames = detector.process_gif(str(gif_path))
    detector.close()

    print(f"✓ {len(skeleton_frames)} Frames erkannt")

    # Stick Figure Rendering
    print("🎨 Rendere Stick Figures...")
    stick_figures_dir = output_dir / "stick_figures"
    stick_figure_paths = StickFigureRenderer.render_sequence(
        skeleton_frames, str(stick_figures_dir)
    )

    print(f"✓ {len(stick_figure_paths)} Stick Figures generiert")

    # Skeleton Daten exportieren
    skeleton_json = output_dir / "skeleton_data.json"
    SkeletonAnalyzer.export_skeleton_data(skeleton_frames, str(skeleton_json))
    print(f"✓ Skeleton-Daten gespeichert: {skeleton_json}")

    # Bewegungsanalyse
    print("📊 Analysiere Bewegungen...")
    motion_analysis = SkeletonAnalyzer.analyze_motion(skeleton_frames)

    # Bewegungsanalyse speichern
    motion_json = output_dir / "motion_analysis.json"
    with open(motion_json, "w") as f:
        json.dump(motion_analysis, f, indent=2)
    print(f"✓ Bewegungsanalyse gespeichert: {motion_json}")

    # Metadaten
    metadata = {
        "source_gif": str(gif_path),
        "frame_count": len(skeleton_frames),
        "stick_figures_dir": str(stick_figures_dir),
        "skeleton_data": str(skeleton_json),
        "motion_analysis": str(motion_json),
        "avg_joints_visible": (
            sum(len(f.visible_joints) for f in skeleton_frames) / len(skeleton_frames)
            if skeleton_frames
            else 0
        ),
    }

    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Analysiere Kampf-GIFs und extrahiere Skelette")
    parser.add_argument("gif", help="Pfad zur GIF-Datei")
    parser.add_argument(
        "-o", "--output", default="output", help="Output-Verzeichnis (default: output)"
    )

    args = parser.parse_args()

    metadata = analyze_gif(args.gif, args.output)

    print("\n" + "=" * 60)
    print("📋 Zusammenfassung")
    print("=" * 60)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
