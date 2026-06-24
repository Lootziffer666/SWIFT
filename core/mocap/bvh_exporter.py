"""
Convert MediaPipe tracking results to BVH (BioVision Hierarchy) format.
BVH is importable by Blender, Unity, Unreal Engine.
"""
import os
import math
from typing import Optional

from core.mocap.video_tracker import TrackingResult, PoseFrame


# BVH skeleton hierarchy using MediaPipe joint names as nodes
# Each entry: (joint_name, parent, channels)
BVH_HIERARCHY = """HIERARCHY
ROOT hips
{
  OFFSET 0.00 0.00 0.00
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT left_hip
  {
    OFFSET -10.00 0.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT left_knee
    {
      OFFSET 0.00 -40.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT left_ankle
      {
        OFFSET 0.00 -40.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0.00 -10.00 0.00
        }
      }
    }
  }
  JOINT right_hip
  {
    OFFSET 10.00 0.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT right_knee
    {
      OFFSET 0.00 -40.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT right_ankle
      {
        OFFSET 0.00 -40.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0.00 -10.00 0.00
        }
      }
    }
  }
  JOINT spine
  {
    OFFSET 0.00 20.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT left_shoulder
    {
      OFFSET -15.00 20.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT left_elbow
      {
        OFFSET 0.00 -30.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT left_wrist
        {
          OFFSET 0.00 -25.00 0.00
          CHANNELS 3 Zrotation Xrotation Yrotation
          End Site
          {
            OFFSET 0.00 -10.00 0.00
          }
        }
      }
    }
    JOINT right_shoulder
    {
      OFFSET 15.00 20.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT right_elbow
      {
        OFFSET 0.00 -30.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT right_wrist
        {
          OFFSET 0.00 -25.00 0.00
          CHANNELS 3 Zrotation Xrotation Yrotation
          End Site
          {
            OFFSET 0.00 -10.00 0.00
          }
        }
      }
    }
    JOINT head
    {
      OFFSET 0.00 25.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {
        OFFSET 0.00 15.00 0.00
      }
    }
  }
}
"""

# Channel order for each joint in MOTION data
JOINT_CHANNEL_ORDER = [
    ("hips",           6),
    ("left_hip",       3), ("left_knee",      3), ("left_ankle",     3),
    ("right_hip",      3), ("right_knee",     3), ("right_ankle",    3),
    ("spine",          3),
    ("left_shoulder",  3), ("left_elbow",     3), ("left_wrist",     3),
    ("right_shoulder", 3), ("right_elbow",    3), ("right_wrist",    3),
    ("head",           3),
]


def _safe_joint(frame: PoseFrame, name: str, fallback=(0.0, 0.0, 0.0)):
    j = frame.joints.get(name)
    if j:
        return j.x * 100, -j.y * 100, j.z * 100  # scale to cm, flip Y
    return fallback


def _angle_between(a, b, c):
    """Compute the angle at joint b given three 3D points a, b, c."""
    ba = (a[0]-b[0], a[1]-b[1], a[2]-b[2])
    bc = (c[0]-b[0], c[1]-b[1], c[2]-b[2])
    dot = sum(ba[i]*bc[i] for i in range(3))
    mag_ba = math.sqrt(sum(x*x for x in ba)) or 1e-9
    mag_bc = math.sqrt(sum(x*x for x in bc)) or 1e-9
    cos_a = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_a))


def _frame_to_motion_line(frame: PoseFrame) -> str:
    """Convert a PoseFrame to one BVH MOTION data line."""
    hips = _safe_joint(frame, "left_hip")
    rh = _safe_joint(frame, "right_hip")
    hip_x = (hips[0] + rh[0]) / 2
    hip_y = (hips[1] + rh[1]) / 2
    hip_z = (hips[2] + rh[2]) / 2

    # Root: position + zero rotation (simplified - real retargeting needs full IK)
    values = [hip_x, hip_y, hip_z, 0.0, 0.0, 0.0]

    # All other joints get zero rotation (placeholder - full conversion needs IK solver)
    remaining_channels = sum(c for _, c in JOINT_CHANNEL_ORDER) - 6
    values += [0.0] * remaining_channels

    return " ".join(f"{v:.4f}" for v in values)


def export_bvh(result: TrackingResult, out_path: str) -> str:
    """Export a TrackingResult as a BVH file."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    frame_time = 1.0 / (result.fps or 24.0)

    lines = [BVH_HIERARCHY, "MOTION"]
    lines.append(f"Frames: {result.total_frames}")
    lines.append(f"Frame Time: {frame_time:.6f}")

    for frame in result.frames:
        lines.append(_frame_to_motion_line(frame))

    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    return out_path
