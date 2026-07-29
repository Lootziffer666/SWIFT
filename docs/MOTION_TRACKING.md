# Motion Tracking & Body Part Segmentation

This document explains how the motion tracking system identifies and validates body parts from skeleton data.

## Overview

The motion tracking system performs three key functions:

1. **Joint Tracking**: Follow individual joints (nose, wrist, ankle, etc.) across consecutive frames
2. **Limb Segmentation**: Group related joints into anatomical limbs (Head, Torso, Arms, Legs)
3. **Anatomical Validation**: Verify that body part structure is physically consistent

## Architecture

### Core Components

#### JointTrack
Tracks a single joint across all frames:
- **positions**: List of (x, y) coordinates normalized to 0-1
- **confidences**: MediaPipe confidence scores for each frame
- **frame_indices**: Which frame each position corresponds to

Methods:
- `get_velocity(frame_idx)`: Calculate pixel/frame movement rate
- `get_distance_traveled()`: Sum of all movements
- `get_confidence_average()`: Overall confidence score
- `is_visible(threshold)`: Is this joint reliably detected?

#### LimbTrack
Groups multiple joints into an anatomical limb:
- Maps to a LimbDefinition (Head, Torso, Left Arm, etc.)
- Contains JointTracks for all relevant joints
- Validates completeness and visibility

Methods:
- `is_complete()`: Has this limb all its joints?
- `is_visible()`: Are ≥70% of joints visible?
- `get_total_movement()`: Sum of movement across all joints
- `get_limb_length(frame_idx)`: Calculate skeleton segment length

#### MotionTracker
Orchestrates the entire tracking system:
- Loads skeleton_data.json from skeleton detection
- Builds JointTrack for each of 17 MediaPipe joints
- Builds LimbTrack for each anatomical limb
- Validates anatomical consistency

## Body Part Definitions

The system defines 6 anatomical limbs:

```
Head (Red: 255, 100, 100)
  - Joints: nose, left_eye, right_eye, left_ear, right_ear

Torso (Green: 100, 255, 100)
  - Joints: left_shoulder, right_shoulder, left_hip, right_hip

Left Arm (Blue: 100, 100, 255)
  - Joints: left_shoulder, left_elbow, left_wrist

Right Arm (Yellow: 255, 255, 100)
  - Joints: right_shoulder, right_elbow, right_wrist

Left Leg (Magenta: 255, 100, 255)
  - Joints: left_hip, left_knee, left_ankle

Right Leg (Cyan: 100, 255, 255)
  - Joints: right_hip, right_knee, right_ankle
```

## Validation Checks

### Anatomical Consistency

The system validates that the skeleton structure is physically possible:

**Arm Length Validation**
- Measures: shoulder → elbow → wrist distance
- Expected: Should remain roughly constant across frames
- Threshold: Variation >30% from mean signals tracking error

**Shoulder Distance Validation**
- Measures: left_shoulder ↔ right_shoulder distance
- Expected: Constant (torso width doesn't change)
- Threshold: Variation >40% from mean signals tracking error

## Usage

### Running Analysis

```bash
# Basic analysis of skeleton data
python core/analyze_motion.py skeleton_data.json

# Output to specific directory
python core/analyze_motion.py skeleton_data.json -o my_reports

# Analyze specific frame range
python core/analyze_motion.py skeleton_data.json --frame-range 275 285

# Focus on high-motion frames only
python core/analyze_motion.py skeleton_data.json --high-motion-only
```

### Interpreting Results

The analysis generates:

1. **motion_tracking_report.txt**: Summary of all limbs
   - Visibility status (✓ VISIBLE or ✗ NOT VISIBLE)
   - Completeness (how many joints detected)
   - Total movement per limb in pixels
   - Per-joint breakdown with distance, confidence, velocity

2. **detailed_motion_analysis.txt**: Full tracking report
   - Anatomical validation results
   - Movement highlights (most active limbs)

3. **limb_sequence_*.png**: Visual representation
   - Multiple consecutive frames rendered horizontally
   - Each limb color-coded consistently
   - Demonstrates body part boundaries and movement

4. **trajectory_*.png**: Joint path visualization
   - Single joint's movement across frames
   - Rendered as connected points on a canvas
   - Brightness indicates confidence score

## Interpreting Visualizations

### Limb Sequence Image

Shows consecutive frames with color-coded limbs:

- **Head (red)**: All points around the face area
- **Torso (green)**: Central shoulder-hip region
- **Arms (blue/yellow)**: Connected lines from shoulders through elbows to wrists
- **Legs (magenta/cyan)**: Connected lines from hips through knees to ankles

Clean assignments mean:
✓ Each joint clearly belongs to one limb
✓ Limbs form continuous chains (shoulder→elbow→wrist)
✓ No joints jumping between limbs frame-to-frame
✓ Movement is smooth and anatomically plausible

### Joint Trajectory Image

Shows a single joint's path over time:

- Grid provides spatial reference
- Points connected by lines show continuous motion
- Darker lines indicate lower confidence
- Gaps suggest the joint was briefly undetected

## Examples

### Detecting a Punch

A clear arm movement (attacking):
1. **Setup frame**: arm at rest, low velocity
2. **Extension frames**: wrist moves 50-100px/frame, elbow follows
3. **Impact frame**: maximum distance from shoulder, velocity peaks
4. **Recovery frames**: arm returns, velocity decreases

Expected motion tracking:
```
Left Arm movement ████████ (high)
- left_shoulder: stationary
- left_elbow: moderate velocity (30-40px)
- left_wrist: high velocity (80-100px)
```

### Detecting a Dodge

A full-body movement:
1. All limbs move together
2. Torso drives motion, limbs follow
3. Low variance in individual joint confidence

Expected motion tracking:
```
All limbs: moderate movement
Torso movement ████ (moderate-high)
Head movement ████ (follows body)
Arms/Legs ██ (secondary motion)
```

## Troubleshooting

### "Assignments Don't Work Cleanly"

If limb boundaries are unclear:

1. **Low confidence**: Check if MediaPipe detected the pose clearly
   - Look for confidence values <0.7 in the report
   - Some frames may need to be filtered out

2. **Joint jumping**: A joint changes limb assignment between frames
   - Indicates tracking ambiguity
   - May need temporal filtering across frames

3. **Incorrect structure**: Joints are grouped wrong
   - Review LIMB_DEFINITIONS in motion_tracker.py
   - Verify joint names match MediaPipe's 17-landmark model

4. **Small movements**: 0.6px/frame movements are difficult to track
   - High-framerate video has small per-frame deltas
   - Analyze frames with larger motion or longer ranges

### Solutions

```python
# In analyze_motion.py, filter low-confidence frames:
if frame_data.get("visible_count", 0) >= 15:  # 15+ of 17 joints visible
    process_frame(frame_data)

# Or aggregate multiple frames:
# Compare every 5 frames instead of every frame
# for i in range(0, frame_count, 5):
#     frame_pair = (frames[i], frames[i+5])
```

## Performance Notes

- Motion tracking runs in O(n) time where n = number of frames
- Memory usage: ~100KB per 100 frames
- For typical 30fps videos: very fast (<100ms)
- For high-framerate (120fps+): may need frame decimation

## Future Enhancements

1. **Temporal Smoothing**: Kalman filter for joint positions
2. **Confidence Weighting**: De-emphasize low-confidence joints
3. **Motion Segmentation**: Auto-detect where motions start/end
4. **Pose Classification**: Identify standard poses (attack, defend, dodge)
5. **Physics Validation**: Check for impossible bone lengths or joint angles
