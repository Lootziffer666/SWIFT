#!/usr/bin/env python3
"""
Analyze motion tracking from skeleton_data.json and generate detailed reports.

Usage:
    python analyze_motion.py skeleton_data.json [--output-dir reports]
"""

import argparse
import sys
from pathlib import Path

from motion_tracker import MotionTracker
from limb_visualizer import draw_limb_sequence, draw_joint_trajectory


def main():
    parser = argparse.ArgumentParser(
        description="Analyze motion tracking from skeleton data"
    )
    parser.add_argument("skeleton_json", help="Path to skeleton_data.json")
    parser.add_argument(
        "-o", "--output-dir", default="motion_reports", help="Output directory for reports"
    )
    parser.add_argument(
        "--frame-range",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Frame range to analyze (default: auto-select frames with motion)",
    )
    parser.add_argument(
        "--high-motion-only",
        action="store_true",
        help="Analyze only frames with highest movement",
    )

    args = parser.parse_args()

    skeleton_file = Path(args.skeleton_json)
    if not skeleton_file.exists():
        print(f"Error: {skeleton_file} not found")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    print(f"Loading skeleton data from {skeleton_file}")
    tracker = MotionTracker(str(skeleton_file))

    # Generate limb summary report
    print("\n" + "=" * 70)
    print("GENERATING MOTION TRACKING REPORT")
    print("=" * 70)

    summary = tracker.get_limb_summary()
    print(summary)

    # Save report
    report_file = output_dir / "motion_tracking_report.txt"
    with open(report_file, "w") as f:
        f.write(summary)
    print(f"\n✓ Report saved to {report_file}")

    # Export full tracking report
    full_report = output_dir / "detailed_motion_analysis.txt"
    tracker.export_tracking_report(str(full_report))
    print(f"✓ Detailed analysis saved to {full_report}")

    # Determine frame range for visualization
    if args.frame_range:
        start_frame, end_frame = args.frame_range
    else:
        # Auto-select frames with most movement
        frame_count = len(tracker.data["frames"])
        if args.high_motion_only:
            # Find 5-frame window with highest movement
            max_movement = 0.0
            best_start = 0
            window_size = min(5, frame_count // 10)

            for i in range(frame_count - window_size):
                movement = sum(
                    tracker.data["frames"][j].get("motion", 0)
                    for j in range(i, i + window_size)
                )
                if movement > max_movement:
                    max_movement = movement
                    best_start = tracker.data["frames"][i]["frame"]

            end_frame = min(
                best_start + window_size, tracker.data["frames"][-1]["frame"]
            )
            start_frame = best_start
        else:
            # Use first and last frames
            start_frame = tracker.data["frames"][0]["frame"]
            end_frame = min(start_frame + 10, tracker.data["frames"][-1]["frame"])

    print(f"\nGenerating limb sequence visualization ({start_frame}-{end_frame})")
    limb_seq_file = output_dir / f"limb_sequence_{start_frame:04d}_{end_frame:04d}.png"
    draw_limb_sequence(
        str(limb_seq_file),
        str(skeleton_file),
        (start_frame, end_frame),
    )

    # Generate joint trajectory visualizations for key joints
    key_joints = [
        "left_wrist",
        "right_wrist",
        "left_ankle",
        "right_ankle",
        "nose",
    ]

    print(f"\nGenerating joint trajectory visualizations...")
    for joint_name in key_joints:
        if joint_name in tracker.joint_tracks:
            traj_file = output_dir / f"trajectory_{joint_name}.png"
            draw_joint_trajectory(
                str(traj_file),
                str(skeleton_file),
                joint_name,
                frame_range=(start_frame, end_frame) if args.frame_range else None,
            )
            print(f"  ✓ {joint_name}: {traj_file}")

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Output directory: {output_dir}")
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*")):
        if f.is_file():
            print(f"  • {f.name}")


if __name__ == "__main__":
    main()
