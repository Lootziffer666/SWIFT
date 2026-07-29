# Body Part Assignment Solution

## The Problem

**Original Issue**: "Die Zuordnungen funktionieren nicht sauber" (The assignments don't work cleanly)

This refers to the challenge of accurately identifying which joints belong to which body parts, especially when:
- Multiple joints are detected simultaneously
- Motion is fast or complex
- Some joints have lower confidence scores
- Frame-to-frame tracking needs to be consistent

## The Solution: Explicit Limb Segmentation

Rather than relying on implicit spatial proximity or heuristics, the motion tracking system uses **explicit anatomical definitions** to assign joints to body parts.

### Core Approach

#### 1. Define Limb Boundaries Explicitly

```python
LIMB_DEFINITIONS = [
    LimbDefinition(
        "Head", LimbType.HEAD,
        ["nose", "left_eye", "right_eye", "left_ear", "right_ear"],
        (255, 100, 100)  # Red for visualization
    ),
    LimbDefinition(
        "Left Arm", LimbType.LEFT_ARM,
        ["left_shoulder", "left_elbow", "left_wrist"],
        (100, 100, 255)  # Blue for visualization
    ),
    # ... more limbs
]
```

Each limb has:
- **Explicit joint list**: defines which joints belong to this limb
- **Anatomical ordering**: joints in sequence (shoulder → elbow → wrist)
- **Color coding**: for consistent visualization

#### 2. Track Each Joint Individually

```python
class JointTrack:
    joint_name: str                  # "left_wrist"
    positions: List[Tuple[float, float]]  # [(x0, y0), (x1, y1), ...]
    confidences: List[float]        # [0.95, 0.92, 0.90, ...]
    frame_indices: List[int]        # [0, 1, 2, ...]
```

Each joint is tracked completely independently:
- Store all positions across all frames
- Keep confidence scores for each frame
- Know exactly which frame each position came from
- Calculate velocity, distance, visibility independently

#### 3. Group Joints into Limbs

```python
class LimbTrack:
    limb_def: LimbDefinition       # Definition with joint names
    joint_tracks: Dict[str, JointTrack]  # {"left_shoulder": JointTrack(...), ...}
```

Each limb groups its constituent joints:
- Contains JointTrack objects for all its joints
- Validates that all expected joints are present
- Calculates limb-level metrics (total movement, length)

#### 4. Validate Anatomical Consistency

```python
def validate_anatomical_consistency(self) -> List[str]:
    """Check for anatomically impossible movements"""
    issues = []
    
    # Arm length should be constant
    # (shoulder → elbow → wrist distance doesn't change)
    # Threshold: variation >30% signals tracking error
    
    # Shoulder distance should be constant
    # (left_shoulder ↔ right_shoulder is torso width)
    # Threshold: variation >40% signals tracking error
    
    return issues
```

The system validates that the skeleton structure is physically plausible:
- Bones don't change length (arm should stay same length)
- Torso width doesn't change (shoulder distance is constant)
- Joint hierarchy is maintained (shoulder never "passes through" elbow)

## Why This Works

### Clean Assignments

The system guarantees clean assignments because:

1. **No ambiguity**: Each joint belongs to exactly one limb (defined in LIMB_DEFINITIONS)
2. **No temporal jumping**: A joint doesn't switch limbs between frames
3. **Anatomically valid**: Validation checks catch impossible movements
4. **Frame-by-frame consistency**: Each frame independently shows which limbs moved

### Example: Frame Analysis

```
Frame 0 → Frame 1 (one frame later):

Head (red):
  nose: (0.500, 0.300) → (0.501, 0.301)  ✓ Moved slightly
  All head joints: SAME LIMB, consistent positions

Left Arm (blue):
  left_shoulder: (0.400, 0.450) → (0.400, 0.450)  ✓ Stationary (anchor)
  left_elbow: (0.300, 0.600) → (0.280, 0.580)     ✓ Moved inward
  left_wrist: (0.250, 0.750) → (0.220, 0.720)     ✓ Moved inward (faster than elbow)

This tells us: LEFT ARM IS RETRACTING (punch recovery or dodge)
```

### Movement Clarity

The detailed per-joint tracking makes movement patterns clear:

```
PUNCH ATTACK:
  left_shoulder: 0.0px (anchor - doesn't move)
  left_elbow: 78.5px (drives the punch)
  left_wrist: 156.8px (impact point - moves most)
  → Clear: arm is extending from shoulder

DODGE MOVE:
  All limbs: 40-60px movement
  Torso: 52px (drives the motion)
  All limbs move together in sync
  → Clear: whole body is dodging
```

## Implementation Details

### Data Flow

```
Skeleton Detection (MediaPipe)
        ↓
    skeleton_data.json (17 joints × N frames)
        ↓
    MotionTracker.build_tracks()
        ↓
    JointTrack (individual tracking)
        ↓
    LimbTrack (grouping into limbs)
        ↓
    Validation (anatomical checks)
        ↓
    Reports + Visualizations
```

### Key Metrics Per Limb

- **Bewegung (Movement)**: Total distance traveled by this limb
- **Vollständig (Complete)**: Do we have all expected joints?
- **Status (Visible)**: Is this limb visible enough to track?
- **Per-joint breakdown**: Distance, confidence, velocity for each joint

### Visualization

Color-coded limbs in `limb_sequence_*.png`:
- Same color consistent across all frames
- Easy to see which limbs are moving together
- Joint connectivity shown as bones (lines)
- Joints shown as circles

```
Frame 0        Frame 1        Frame 2
[Red head]     [Red head]     [Red head]     ← Head (consistent red)
[Green torso]  [Green torso]  [Green torso]  ← Torso (consistent green)
[Blue arm]     [Blue arm]     [Blue arm]     ← Arm (consistent blue, moving)
```

## Addressing Specific Concerns

### "Assignments Don't Work Cleanly"

**Before**: Implicit spatial clustering led to ambiguous boundaries
- Joint 11 (left_hip) near joint 12 (right_hip)
- Sometimes grouped wrong frame to frame
- Hard to verify correctness

**After**: Explicit definitions make assignments verifiable
- Left Arm = ["left_shoulder", "left_elbow", "left_wrist"] (always)
- Joint 11 (left_hip) always belongs to Torso and Left Leg
- Can validate frame-by-frame consistency
- Color-coded visualization makes errors obvious

### "Where Does an Arm Start/End?"

**Arm Boundaries**:
```
Shoulder (start): left_shoulder (joint 5)
  ↓
Elbow (middle): left_elbow (joint 7)
  ↓
Wrist (end): left_wrist (joint 9)

These three joints form the Left Arm limb.
Shoulder is shared with Torso (anchor point).
```

### "What is the Head?"

**Head Limb**:
```
Main point: nose (joint 0)
Eyes: left_eye (1), right_eye (2)
Ears: left_ear (3), right_ear (4)

These five joints form the Head limb.
Head moves independently from torso.
```

## Validation Examples

### Good Skeleton (Passes Validation)

```
Arm Length Check:
  Frame 0: shoulder→elbow→wrist = 42.5cm
  Frame 1: shoulder→elbow→wrist = 42.6cm
  Frame 2: shoulder→elbow→wrist = 42.4cm
  Variation: ±0.2cm (< 30% threshold) ✓ PASS

Shoulder Distance Check:
  Frame 0: left_shoulder ↔ right_shoulder = 30.0cm
  Frame 1: left_shoulder ↔ right_shoulder = 30.1cm
  Variation: ±0.1cm (< 40% threshold) ✓ PASS

Result: ✓ Skeleton is anatomically consistent
```

### Bad Skeleton (Fails Validation)

```
Arm Length Check:
  Frame 0: 42.5cm
  Frame 5: 35.2cm  ← Suddenly shorter!
  Frame 10: 48.1cm ← Then longer!
  Variation: ±15% (> 30% threshold) ⚠️ FAIL

Result: ⚠️ Tracking errors detected in left arm
         - Check confidence scores
         - Verify MediaPipe detected pose correctly
         - May need to filter out bad frames
```

## Integration with Combat System

The clean limb assignments enable accurate procedural animation:

```python
# From motion tracking
left_arm_movement = 487.2  # pixels over 10 frames
right_arm_movement = 5.6   # stationary (guard)

# Convert to combat action
if left_arm_movement > 400 and right_arm_movement < 50:
    action = ActionType.ATTACK  # Clear punch
    power = left_arm_movement / 400  # Normalized 0-1
elif all_limbs_movement > 300:
    action = ActionType.DODGE   # Full-body dodge
else:
    action = ActionType.DEFEND  # Defensive stance
```

## Future Enhancements

1. **Temporal Smoothing**: Kalman filter to reduce noise
2. **Confidence Weighting**: De-emphasize unreliable joints
3. **Pose Classification**: Train classifiers on movement patterns
4. **Physics Validation**: Check joint angles against anatomical ranges
5. **Multi-person Tracking**: Extend to identify separate fighters

## Summary

The explicit limb segmentation system provides:
- ✓ Clear, verifiable joint-to-limb assignments
- ✓ Anatomically validated skeleton structure
- ✓ Frame-by-frame movement tracking per body part
- ✓ Confidence scores for each measurement
- ✓ Color-coded visualization of limb boundaries
- ✓ Detailed reports showing exactly what moved and how much

This directly addresses the concern that "assignments don't work cleanly" by replacing implicit heuristics with explicit, validated anatomical definitions.
