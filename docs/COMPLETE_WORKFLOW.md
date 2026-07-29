# Complete Workflow: From Fight GIF to Playable Combat

This document shows the complete pipeline from a motion-capture fight animation GIF to playable turn-based combat.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│ Step 1: Skeleton Detection                              │
│ Input: fight.gif                                        │
│ Output: skeleton_data.json                              │
│         stick_figures/                                  │
│         skeleton_visualizations/                        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2: Motion Tracking & Body Part Analysis            │
│ Input: skeleton_data.json                               │
│ Output: motion_tracking_report.txt                      │
│         limb_sequence_*.png (colored body parts)        │
│         trajectory_*.png (joint paths)                  │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 3: Action Pattern Recognition                      │
│ Input: motion tracking reports                          │
│ Output: identified actions (punch, kick, dodge, etc.)   │
│         frame ranges for each action                    │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 4: Procedural Pose Generation                      │
│ Input: skeleton_data.json + identified actions          │
│ Output: action_poses.json                               │
│         Multi-style renders:                            │
│         - Stick figures                                 │
│         - Sketches                                      │
│         - Cartoon                                       │
│         - Realistic                                     │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 5: Combat System Integration                       │
│ Input: action poses + combat engine                     │
│ Output: playable turn-based combat                      │
│         Real-time web UI                                │
│         Damage calculations                             │
│         Victory/defeat conditions                       │
└─────────────────────────────────────────────────────────┘
```

## Detailed Workflow

### Step 1: Extract Skeleton from GIF

```bash
# Analyze the fight GIF and extract skeleton data
python core/gif_analyzer.py fight.gif -o skeleton_data.json

# This produces:
# - skeleton_data.json: All joint positions for all frames
# - stick_figures/: Rendered skeleton as stick figures
# - skeleton_metadata.json: Frame count, visible joint stats
```

**What happens**:
1. Opens the GIF and reads frame by frame
2. For each frame, runs MediaPipe Pose detection
3. Extracts 17 joint positions (normalized 0-1)
4. Stores confidence scores for each joint
5. Renders stick figures with detected skeletons

**Output example (skeleton_data.json)**:
```json
{
  "version": "1.0",
  "frame_count": 300,
  "joint_names": ["nose", "left_eye", "right_eye", ...],
  "frames": [
    {
      "frame": 0,
      "joints": {
        "nose": [0.5, 0.3, 0.95],          // x, y, confidence
        "left_shoulder": [0.4, 0.45, 0.94],
        "left_elbow": [0.3, 0.6, 0.91],
        "left_wrist": [0.25, 0.75, 0.85],
        // ... 17 joints total
      }
    },
    // ... 300 frames
  ]
}
```

### Step 2: Track Body Part Movements

```bash
# Analyze skeleton data to track individual body parts
python core/analyze_motion.py skeleton_data.json -o motion_reports

# This produces:
# - motion_tracking_report.txt: Detailed per-limb analysis
# - limb_sequence_*.png: Color-coded body parts
# - trajectory_*.png: Individual joint paths
# - detailed_motion_analysis.txt: Full analysis with validation
```

**What happens**:
1. Creates JointTrack for each of 17 joints
2. Groups joints into 6 limbs (Head, Torso, Arms×2, Legs×2)
3. Calculates movement metrics per limb
4. Validates anatomical consistency
5. Generates visualizations

**Output example (motion_tracking_report.txt)**:
```
Head (head)
  Status: ✓ VISIBLE
  Vollständig: ✓ (5/5 Joints)
  Bewegung: 12.34 Pixel
    • nose                 Dist=  5.67px  Conf=98.5%  Vel=0.08px/f
    • left_eye             Dist=  5.45px  Conf=97.2%  Vel=0.08px/f
    ...

Left Arm (left_arm)
  Status: ✓ VISIBLE
  Vollständig: ✓ (3/3 Joints)
  Bewegung: 234.56 Pixel  ← This arm is moving!
    • left_shoulder        Dist=  1.23px  Conf=99.1%  Vel=0.02px/f
    • left_elbow           Dist=112.34px  Conf=96.3%  Vel=1.60px/f  ← Elbow moving
    • left_wrist           Dist=234.56px  Conf=94.7%  Vel=3.35px/f  ← Wrist fastest
```

### Step 3: Identify Action Patterns

```python
# Manually review motion tracking reports to identify actions
# Look for characteristic movement patterns:

# PUNCH (Attack):
#   - One arm: large movement (200-400px)
#   - Other arm: small movement (<50px)
#   - Shoulder: stationary
#   - Wrist: highest velocity

# KICK:
#   - One leg: large movement (300-500px)
#   - Torso: small movement
#   - Hip: stationary anchor
#   - Ankle: highest velocity

# DODGE:
#   - All limbs: moderate movement (100-200px)
#   - All limbs move together (synchronized)
#   - Head follows body
#   - Torso drives motion

# DEFEND:
#   - Both arms: raised, moving together
#   - Legs: stationary
#   - Shoulders: up and forward
```

**Create action mapping file**:
```json
{
  "actions": [
    {
      "type": "attack",
      "name": "Punch Right",
      "frame_range": [50, 80],
      "limb": "right_arm",
      "power": 0.8
    },
    {
      "type": "attack",
      "name": "Kick Left",
      "frame_range": [120, 160],
      "limb": "left_leg",
      "power": 1.0
    },
    {
      "type": "dodge",
      "name": "Dodge Left",
      "frame_range": [200, 230],
      "power": 0.6
    },
    {
      "type": "defend",
      "name": "Guard",
      "frame_range": [240, 300],
      "power": 0.5
    }
  ]
}
```

### Step 4: Generate Procedural Poses

```python
from procedural_rigging import ProceduralRig, ActionType, RenderStyle

# Load the skeleton and create a rig
rig = ProceduralRig("skeleton_data.json")

# Generate poses for each action
actions_config = {
    ActionType.ATTACK: (50, 80),      # frame range for attack pose
    ActionType.DEFEND: (240, 300),    # frame range for defend pose
    ActionType.DODGE: (200, 230),     # frame range for dodge pose
}

# Generate and save poses in multiple styles
for action_type, (start, end) in actions_config.items():
    # Get pose from middle of action sequence
    mid_frame = (start + end) // 2
    pose = rig.pose_for_action(action_type)
    
    # Render in multiple styles
    for style in [RenderStyle.STICK, RenderStyle.SKETCH, RenderStyle.CARTOON]:
        output_file = f"poses/{action_type.value}_{style.value}.png"
        pose.render(output_file, style=style)
```

**This generates**:
```
poses/
├── attack_stick.png      (Stick figure)
├── attack_sketch.png     (Sketch style)
├── attack_cartoon.png    (Cartoon style)
├── defend_stick.png
├── defend_sketch.png
├── defend_cartoon.png
└── ...
```

### Step 5: Integrate with Combat Engine

```python
from combat_engine import CombatEngine, ActionType

# Initialize combat with our fighter poses
engine = CombatEngine(
    fighter1_skeleton="skeleton_data.json",
    fighter2_skeleton="skeleton_data.json",  # Same fighter for demo
    fighter1_name="Fighter A",
    fighter2_name="Fighter B"
)

# Simulate a combat turn
print(engine.execute_turn(
    fighter1_action=ActionType.ATTACK,
    fighter2_action=ActionType.DEFEND
))

# Output:
# {
#   "fighter1": {
#     "name": "Fighter A",
#     "action": "ATTACK",
#     "damage_dealt": 24,
#     "damage_taken": 8,  # From counter
#     "hp": 92,
#     "status": "healthy"
#   },
#   "fighter2": {
#     "name": "Fighter B",
#     "action": "DEFEND",
#     "damage_dealt": 8,
#     "damage_taken": 24,
#     "hp": 76,
#     "status": "damaged"
#   }
# }
```

### Step 6: Launch Web Interface

```bash
# Start the FastAPI backend
python web/app.py

# Open browser to http://localhost:8000
# Access the combat demo at /static/combat.html
```

**Features**:
- ✓ Real-time combat simulation
- ✓ Health bars and damage display
- ✓ Turn log with move history
- ✓ Skeleton visualization
- ✓ Multiple render styles (toggle via UI)

## Example: Complete Fight Sequence

### Frame Analysis

```
Frames 0-50: SETUP (idle pose)
  Movement: Minimal (<5px per limb)
  All limbs: stationary
  Type: Idle stance

Frames 50-80: ATTACK (punch)
  Left Arm movement: 234.56px  ← BIG MOVEMENT
  Right Arm movement: 5.67px   ← Guarding
  Torso movement: 2.34px       ← Stationary
  Result: CLEAR PUNCH ACTION

Frames 80-120: RECOVERY (returning to guard)
  All arm movement: decreasing
  Shoulders: returning to position
  Type: Recovery stance

Frames 120-160: KICK (leg attack)
  Left Leg movement: 345.67px  ← BIG MOVEMENT
  Right Leg movement: 45.67px  ← Supporting
  Torso movement: 89.12px      ← Rotates for kick
  Result: CLEAR KICK ACTION

Frames 160-200: DODGE (full body)
  All limbs movement: 150-200px
  All limbs synchronized
  Torso drives motion: 180px
  Result: CLEAR DODGE ACTION
```

### Combat Simulation

```python
# Based on identified actions, execute combat:

Turn 1:
  Fighter A: ATTACK (Punch Right)
  Fighter B: DEFEND
  Result: Fighter A deals 24 damage, takes 8 counter-damage

Turn 2:
  Fighter A: DEFEND
  Fighter B: ATTACK (Kick Left)
  Result: Fighter B deals 28 damage, takes 2 counter-damage

Turn 3:
  Fighter A: DODGE
  Fighter B: ATTACK (Punch Right)
  Result: Dodge success! Fighter A takes 0 damage, Fighter B damaged 5 (miss)

Turn 4:
  Fighter A: ATTACK (Kick Left)
  Fighter B: ATTACK (Punch Right)
  Result: Both land! A deals 25, B deals 22

// Continue until one fighter defeated...

Final:
  Fighter A: 45 HP remaining (Victory!)
  Fighter B: 0 HP (Defeated)
```

## Quality Checklist

Before declaring motion tracking "clean", verify:

- [ ] All limbs identified (6 limbs complete)
- [ ] All joints detected (17 joints, high confidence >0.8)
- [ ] Anatomical validation passes
  - [ ] Arm length consistent (±30% variation OK)
  - [ ] Shoulder distance constant (±40% variation OK)
- [ ] Action patterns are clear
  - [ ] Punch: one arm >200px movement, opposite <50px
  - [ ] Kick: one leg >300px movement, opposite <50px
  - [ ] Dodge: all limbs 100-200px, synchronized
  - [ ] Defend: both arms raised, legs stationary
- [ ] Visualization is clear
  - [ ] Color-coded limbs are consistent
  - [ ] Joint trajectories show smooth motion
  - [ ] No joint jumping between limbs

## Troubleshooting

### "Movement is too small (0.6px/frame)"

**Cause**: High-framerate video or slow motion
**Solution**:
- Analyze larger frame ranges (50-100 frames instead of 5-10)
- Look for frames with peak velocity
- Or: Sample every Nth frame instead of every frame

### "Some frames have low confidence (<0.3)"

**Cause**: Partial occlusion or poor lighting
**Solution**:
- Filter out frames with <15 visible joints
- Focus on high-quality frames (>16 visible joints)
- Or: Use temporal smoothing (Kalman filter)

### "Anatomical validation fails"

**Cause**: Tracking errors in low-confidence frames
**Solution**:
- Check confidence scores per joint
- Identify frames with tracking loss
- Filter out problematic frames
- Or: Increase confidence threshold (0.5 instead of 0.3)

### "Action patterns not clear"

**Cause**: GIF has slow motion or transitional frames
**Solution**:
- Look for frames with highest velocity (peak action)
- Ignore setup/recovery frames
- Focus on 5-10 frame windows around peak movement
- Or: Aggregate multiple punches/kicks to find average pattern

## Next Steps

Once the workflow is complete:

1. **Train classifiers**: Use motion data to classify actions
2. **Add variation**: Generate different punch/kick styles
3. **Multi-fighter**: Support different fighters with different move sets
4. **Realistic rendering**: Upgrade from stick figures to full 3D models
5. **Physics**: Add ragdoll physics for knockdowns
6. **Networking**: Multiplayer turn-based combat
7. **Mobile**: Deploy as web app or native app

## Files Generated

```
project/
├── skeleton_data.json                    ← Step 1
├── stick_figures/
│   ├── stick_0000.png
│   ├── stick_0001.png
│   └── ...
├── motion_reports/                       ← Step 2
│   ├── motion_tracking_report.txt
│   ├── limb_sequence_*.png
│   └── trajectory_*.png
├── actions.json                          ← Step 3
└── poses/                                ← Step 4
    ├── attack_stick.png
    ├── attack_sketch.png
    ├── defend_sketch.png
    └── ...
```

## Performance Notes

- **Step 1 (Skeleton Detection)**: ~2-5 seconds per 100 frames
- **Step 2 (Motion Tracking)**: <100ms for 300 frames
- **Step 3 (Pattern Recognition)**: Manual (5-10 minutes)
- **Step 4 (Pose Generation)**: ~1 second per pose
- **Step 5 (Combat Simulation)**: Real-time (100ms per turn)

Total pipeline: ~10-20 minutes from GIF to playable combat.
