# Motion Tracking Quick Start

This guide shows how to use the motion tracking system to analyze body part movements from skeleton data.

## Installation

The motion tracking system requires scipy for distance calculations:

```bash
pip install -r requirements.txt
```

## Basic Usage

### 1. Extract Skeleton from GIF

First, extract skeleton data from your fight animation GIF:

```bash
python core/gif_analyzer.py my_fight.gif -o skeleton_data.json
```

This creates:
- `skeleton_data.json`: Joint positions for all frames
- `stick_figures/`: Rendered stick figure frames
- `skeleton_metadata.json`: Analysis of the GIF

### 2. Run Motion Tracking Analysis

Analyze the skeleton data to identify body part movements:

```bash
python core/analyze_motion.py skeleton_data.json -o motion_reports
```

### 3. Interpret Results

The analysis generates:

**motion_tracking_report.txt**:
```
Head (head)
  Status: ✓ SICHTBAR (VISIBLE)
  Vollständig: ✓ (5/5 Joints)
  Bewegung: 26.13 Pixel (über 10 Frames)
    • nose                 Dist= 8.34px  Conf=98.5%  Vel=0.12px/f
    • left_eye             Dist= 7.92px  Conf=97.2%  Vel=0.11px/f
    ...

Left Arm (left_arm)
  Status: ✓ SICHTBAR
  Vollständig: ✓ (3/3 Joints)
  Bewegung: 156.78 Pixel (über 10 Frames)  ← Large movement!
    • left_shoulder        Dist= 0.00px  Conf=99.1%  Vel=0.00px/f
    • left_elbow           Dist= 78.45px Conf=96.3%  Vel=0.56px/f  ← Moving!
    • left_wrist           Dist=156.78px Conf=94.7%  Vel=1.12px/f  ← Moving fast!
```

Read this as:
- ✓ SICHTBAR = Body part is visible and tracked
- 5/5 Joints = All joints for this limb were detected
- Bewegung = Total pixel distance traveled
- Dist = Per-joint movement
- Conf = Confidence score (0.3+ is good, 0.8+ is excellent)
- Vel = Velocity in pixels per frame

**limb_sequence_*.png**:
- Shows multiple frames rendered horizontally
- Each body part color-coded consistently
- Red = Head, Green = Torso, Blue/Yellow = Arms, Magenta/Cyan = Legs
- Watch how each limb moves separately

**trajectory_*.png**:
- Shows a single joint's path over time
- Grid provides spatial reference
- Connected dots show continuous motion
- Darker = lower confidence, brighter = higher confidence

## Advanced Usage

### Analyze Specific Frames

Focus analysis on a particular action sequence:

```bash
python core/analyze_motion.py skeleton_data.json --frame-range 50 75
```

### Find High-Motion Sequences

Automatically select frames with the most action:

```bash
python core/analyze_motion.py skeleton_data.json --high-motion-only
```

### Using Motion Data in Code

```python
from motion_tracker import MotionTracker

# Load and analyze
tracker = MotionTracker("skeleton_data.json")

# Get a specific limb
left_arm = tracker.limb_tracks["Left Arm"]

# Check if visible
if left_arm.is_visible():
    # Get movement amount
    movement = left_arm.get_total_movement()
    print(f"Left arm moved {movement:.1f} pixels")
    
    # Check individual joint
    wrist_track = left_arm.joint_tracks["left_wrist"]
    distance = wrist_track.get_distance_traveled()
    velocity = wrist_track.get_velocity(frame_idx=42, window=3)
    print(f"Wrist: {distance:.1f}px, velocity: {velocity}")

# Validate anatomy
issues = tracker.validate_anatomical_consistency()
if issues:
    for issue in issues:
        print(f"⚠️  {issue}")
else:
    print("✓ Skeleton structure is anatomically consistent")

# Get most moving limb
result = tracker.find_most_moving_limb()
if result:
    limb_name, movement = result
    print(f"Most moving: {limb_name} ({movement:.1f}px)")
```

## Example: Detecting a Punch

Given skeleton data of a punch attack, the motion tracking shows:

```
Left Arm (left_arm)
  Status: ✓ SICHTBAR
  Vollständig: ✓ (3/3 Joints)
  Bewegung: 487.23 Pixel  ← BIG MOVEMENT!
    • left_shoulder        Dist=  2.34px  Conf=99.1%  Vel=0.02px/f  ← Anchor
    • left_elbow           Dist=234.56px  Conf=97.5%  Vel=1.68px/f  ← Drives punch
    • left_wrist           Dist=487.23px  Conf=95.2%  Vel=3.48px/f  ← Fast!

Right Arm (right_arm)
  Status: ✓ SICHTBAR
  Vollständig: ✓ (3/3 Joints)
  Bewegung: 5.67 Pixel   ← MINIMAL MOVEMENT
    • right_shoulder       Dist=  0.12px  Conf=99.0%  Vel=0.00px/f  ← Stationary
    • right_elbow          Dist=  2.34px  Conf=96.8%  Vel=0.02px/f  ← Slight move
    • right_wrist          Dist=  5.67px  Conf=95.1%  Vel=0.04px/f  ← Guard
```

This clearly shows:
- Left arm attacking (487px movement, wrist velocity 3.48px/f)
- Right arm defending (5.67px movement, wrist stationary)
- Shoulder stays planted (anchor point)

## Example: Detecting a Dodge

For a full-body dodge movement:

```
Head (head)
  Bewegung: 45.23 Pixel  ← Head follows body

Torso (torso)
  Bewegung: 52.11 Pixel  ← Drives the dodge

Left Arm (left_arm)
  Bewegung: 48.56 Pixel  ← Arms follow

Right Arm (right_arm)
  Bewegung: 51.23 Pixel  ← Symmetric

Left Leg (left_leg)
  Bewegung: 34.67 Pixel  ← Legs support

Right Leg (right_leg)
  Bewegung: 36.12 Pixel  ← Symmetric
```

This shows all limbs moving together (coordinated), with torso driving the motion.

## Troubleshooting

### "Assignments Don't Work Cleanly"

If joints appear to jump between limbs or limb boundaries are unclear:

1. **Check frame visibility**
   ```python
   for frame in tracker.data["frames"]:
       visible = frame.get("visible_count", 0)
       if visible >= 15:  # 15+ of 17 joints visible
           print(f"Frame {frame['frame']}: OK ({visible}/17)")
   ```

2. **Look for low-confidence frames**
   ```python
   for limb_name, limb_track in tracker.limb_tracks.items():
       avg_conf = sum(
           jt.get_confidence_average() 
           for jt in limb_track.joint_tracks.values()
       ) / len(limb_track.joint_tracks)
       print(f"{limb_name}: {avg_conf:.1%} confidence")
   ```

3. **Filter low-confidence data**
   ```python
   # Only analyze frames where most joints are visible
   high_quality_frames = [
       f for f in tracker.data["frames"]
       if f.get("visible_count", 0) >= 15
   ]
   ```

### Very Small Movements (0.6px/frame)

This suggests:
- **High-framerate video** (60fps+): movements per frame are small
- **Solution**: Analyze larger frame ranges or sum movement over multiple frames
- **Or**: Select frames with peak action (highest velocity)

### Anatomical Warnings

If you see warnings like "Arm length varies too much", this indicates:
- **Tracking errors**: MediaPipe lost the pose in some frames
- **Solution**: Check confidence scores for affected joints
- **Or**: Use only high-confidence frame ranges

## Next Steps

Once motion tracking is working:

1. **Identify Actions**: Find frames with characteristic movement patterns
   - Punch: Large wrist/elbow movement, stationary shoulder
   - Kick: Large ankle/knee movement, small torso movement
   - Dodge: All limbs move together, shoulder/hip distance constant

2. **Generate Poses**: Use procedural_rigging.py to create game poses
   ```python
   from procedural_rigging import ProceduralRig, ActionType
   
   rig = ProceduralRig("skeleton_data.json")
   
   # Get attack pose
   attack_pose = rig.pose_for_action(ActionType.ATTACK, facing_left=True)
   attack_pose.render_to_image("attack_pose.png")
   ```

3. **Train Classifiers**: Feed movement data to classify actions
   ```python
   # Use motion stats as features
   features = [
       left_arm.get_total_movement(),
       right_arm.get_total_movement(),
       torso.get_total_movement(),
       # ... more features
   ]
   ```

## API Reference

See `docs/MOTION_TRACKING.md` for detailed API documentation and examples.
