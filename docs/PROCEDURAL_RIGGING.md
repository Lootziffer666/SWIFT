# Procedural Rigging System · Skelett-zu-Animation Pipeline

## Übersicht

Das **Procedural Rigging System** transformiert echte Motion-Capture Daten in spielbare Kampf-Animationen. Der Workflow:

```
Motion-Capture Videos/GIFs
        ↓
Skeleton Detection (MediaPipe Pose)
        ↓
Joint Position Extraction (17 Landmarks)
        ↓
Procedural Pose Generation (basierend auf Combat State)
        ↓
Multi-Style Rendering
    ├─ Stick Figure (minimal)
    ├─ Sketch (grobe Zeichnungen)
    ├─ Cartoon (animiert)
    └─ Realistic (hochqualität)
        ↓
Real-Time Combat Animation
```

Das System erlaubt es, **aus einer einzigen Motion-Capture Aufnahme** verschiedenste Kampf-Posen zu generieren, ohne aufwendiges Keyframing.

---

## Phase 1: Skeleton Detection

### MediaPipe Pose Recognition

Nutzt Google's **MediaPipe Pose** zur Echtzeit-Skelett-Erkennung:

```python
from core.skeleton_detector import SkeletonDetector

detector = SkeletonDetector()
skeleton_frames = detector.process_gif("fight.gif")
# Gibt: List[SkeletonFrame] mit 17 Joints pro Frame
```

**Erkannte Joints** (17 Landmarks):
```
0   nose
1   left_eye           5   left_shoulder      9   left_wrist
2   right_eye          6   right_shoulder     10  right_wrist
3   left_ear           7   left_elbow         11  left_hip
4   right_ear          8   right_elbow        12  right_hip
                                              13  left_knee
                                              14  right_knee
                                              15  left_ankle
                                              16  right_ankle
```

### Ausgabe: Skeleton Data (JSON)

```json
{
  "version": "1.0",
  "frame_count": 53,
  "joint_names": ["nose", "left_eye", ...],
  "connections": [[0,1], [0,2], [1,3], ...],
  "frames": [
    {
      "frame": 0,
      "width": 400,
      "height": 400,
      "joints": {
        "nose": [0.5, 0.2, 0.95],      // [x, y, confidence]
        "left_shoulder": [0.35, 0.35, 0.92],
        ...
      }
    },
    ...
  ]
}
```

### CLI Usage

```bash
python core/gif_analyzer.py combat.gif -o output/
# Output:
#   output/skeleton_data.json        (Rohdaten)
#   output/stick_figures/            (PNG Frames)
#   output/motion_analysis.json      (Bewegungsstatistik)
#   output/metadata.json             (Zusammenfassung)
```

---

## Phase 2: Procedural Pose Generation

### ProceduralRig: Action → Pose

Statt vorgefertigter Animationen — **algorithmische Pose-Generierung**:

```python
from core.procedural_rigging import ProceduralRig, RenderStyle

# Lade Skeleton-Daten
rig = ProceduralRig("skeleton_data.json")

# Generiere Pose für Attack-Aktion
attack_pose = rig.pose_for_action("attack", facing_right=True, intensity=0.5)

# Rendere als Stick Figure
img = rig.render_pose(attack_pose, width=256, height=256, style=RenderStyle.STICK)
img.save("attack_frame.png")
```

### Action-Mapping

Die Skeleton-Frames werden **zeitlich auf Aktionen verteilt**:

| Action  | Frame-Range | Interpretation |
|---------|-------------|-----------------|
| ATTACK  | 0–33%       | Angriffs-Bewegung |
| DEFEND  | 33–66%      | Defensive Pose |
| DODGE   | 66–100%     | Ausweich-Manöver |
| WAIT    | 50% (center)| Neutrale Haltung |

**Intensität (0–1)** steuert den Fortschritt innerhalb der Range.

### Pose Interpolation

Zwischen zwei Frames linear interpolieren:

```python
pose_a = rig.frames[10]
pose_b = rig.frames[20]

interpolated = pose_a.interpolate_to(pose_b, t=0.5)  # 50% Weg zwischen A und B
```

### Facing Direction (Mirror)

Für Kämpfer in verschiedenen Blickrichtungen:

```python
attack_pose = rig.pose_for_action("attack", facing_right=False)
# Spiegelt alle Joint-Positionen automatisch
```

---

## Phase 3: Multi-Style Rendering

Verschiedene Rendering-Stile aus den **gleichen Skeleton-Daten**:

### Style: STICK (aktuell)

```python
rig.render_pose(pose, style=RenderStyle.STICK)
# Minimal: Linien zwischen Joints
# Farben: Grau=Knochen, Rot=Gelenke
```

### Style: SKETCH (in Entwicklung)

```python
rig.render_pose(pose, style=RenderStyle.SKETCH)
# Dickere Linien, grobe Zeichnungen
# Vorbereitung für Charakter-Outlines
```

### Style: CARTOON (Roadmap)

```python
rig.render_pose(pose, style=RenderStyle.CARTOON)
# Mit Blender Shader-Integration
# NPR (Non-Photorealistic Rendering)
# Outline + Color Quantization
```

### Style: REALISTIC (Roadmap)

```python
rig.render_pose(pose, style=RenderStyle.REALISTIC)
# Original Motion-Capture Quality
# Mesh + Textur Rendering via Blender
```

---

## Phase 4: Combat Animation Compiler

Kompiliert Turn-Logik zu Animation Frames:

```python
from core.procedural_rigging import CombatAnimationCompiler

compiler = CombatAnimationCompiler(rig1, rig2)

# Generiere 12-Frame Animation für einen Turn
frames = compiler.compile_turn(
    fighter1_action="attack",
    fighter2_action="defend",
    frame_count=12,
    width=256,
    height=256
)

# frames: List[(Image_fighter1, Image_fighter2), ...]
```

### Real-Time in Web

```javascript
// combatEngine liefert Actions
const turnResult = await fetch("/api/combat/action/...");

// ProceduralRig generiert Frames
const frames = await compilePoses(
  fighter1Action,
  fighter2Action
);

// Zeige Animation auf Canvas
playAnimationSequence(frames, fps=12);
```

---

## Praktische Beispiele

### Beispiel 1: Kampf-Sequenz generieren

```python
from core.procedural_rigging import ProceduralRig

# Lade beide Kämpfer
hero_rig = ProceduralRig("hero_skeleton.json")
villain_rig = ProceduralRig("villain_skeleton.json")

# Generiere Attack + Defend Posen
hero_attack = hero_rig.pose_for_action("attack", intensity=1.0)
villain_defend = villain_rig.pose_for_action("defend", intensity=1.0, facing_right=False)

# Rendere nebeneinander
hero_img = hero_rig.render_pose(hero_attack, width=256)
villain_img = villain_rig.render_pose(villain_defend, width=256)

# Kombiniere zu Battle-Frame
combined = Image.new("RGB", (512, 256))
combined.paste(hero_img, (0, 0))
combined.paste(villain_img, (256, 0))
combined.save("battle_frame.png")
```

### Beispiel 2: Charaktervariationen

```python
# Gleiche Skeleton-Daten, verschiedene Renders
base_pose = rig.pose_for_action("attack")

stick_img = rig.render_pose(base_pose, style=RenderStyle.STICK)
sketch_img = rig.render_pose(base_pose, style=RenderStyle.SKETCH)

# Verschiedene Charaktere aus gleicher Motion!
stick_img.save("skeleton_attack.png")
sketch_img.save("sketch_attack.png")
```

---

## Datenfluss: Vom GIF zur Sprite-Sheet

```
INPUT: combat.gif (hochwertige Motion-Capture)
  ↓
1. ANALYZE
   python core/gif_analyzer.py combat.gif -o output/
   → skeleton_data.json (1414 Frames × 17 Joints)
  ↓
2. FILTER & SELECT
   Beste Frames auswählen (höchste Confidence)
   Pose-Normalisierung
  ↓
3. PROCEDURAL GENERATION
   rig = ProceduralRig("skeleton_data.json")
   attack_pose = rig.pose_for_action("attack")
   defend_pose = rig.pose_for_action("defend")
   ...
  ↓
4. RENDER
   Stick Figures → Sketches → Cartoons → Realistic
  ↓
5. SPRITE SHEET
   Alle Frames zu PNG/GIF kombinieren
   Manifest generieren (wie SWIFT's standard output)
  ↓
6. INTEGRATION
   Sprite-Sheet in Combat-System laden
   Aktionen triggern die passenden Animationen
  ↓
OUTPUT: spielbare Kampf-Animationen in Echtzeit
```

---

## Erweiterungen (Roadmap)

### 1. Image Preprocessing

```python
def preprocess_frame(frame):
    # Brightness/Contrast für bessere Detection
    # Pose refinement via temporal smoothing
    # Multi-person pose tracking
```

### 2. IK (Inverse Kinematics)

```python
# Berechne Arm-Positionen basierend auf "Gegner treffen"
target_pos = (opponent_x, opponent_y)
arm_pose = rig.solve_ik_for_target(target_pos)
```

### 3. Blender Integration

```python
# Generiere 3D-Posen direkt
blender_armature = rig.export_to_blender()
# Rendere via Blender Cycles für beste Qualität
```

### 4. AI-Generated Animations

```python
# Falls Skeleton zu schlecht erkannt
# Nutze generative Modelle für fehlende Frames
missing_frames = inpaint_missing_poses(skeleton_sequence)
```

### 5. Procedural Variation

```python
# Variere Poses basierend auf Charaktertyp
warrior_stance = rig.apply_archetype("warrior")
rogue_stance = rig.apply_archetype("rogue")
```

---

## Performance & Optimization

### Caching

```python
# Skeleton-Daten cachen (groß, aber statisch)
@lru_cache(maxsize=128)
def load_skeleton(filepath):
    return ProceduralRig(filepath)
```

### Rendering

- **Stick Figures**: ~1ms pro Frame (PIL)
- **Sketch**: ~5ms (dickere Linien)
- **Cartoon**: ~100ms (Blender, aber nur 1x pro Pose)
- **Realistic**: ~500ms (hochwertig)

Für Echtzeit: **Pre-render** oder **GPU accelerate**.

---

## Testing

```bash
python -m pytest tests/test_procedural_rigging.py
```

Tests:
- Skeleton loading & parsing
- Pose generation für alle Actions
- Rendering output validity
- Interpolation accuracy

---

## Zusammenfassung

Statt **vorgefertigte Animationen** → **algorithmische Pose-Synthese aus Motion-Capture**.

**Ein Video** kann **unendlich viele Variationen** generieren:
- Verschiedene Kampf-Aktionen
- Verschiedene Charaktertypen  
- Verschiedene Rendering-Stile
- Verschiedene Intensitäten

Das ist die Zukunft proceduraler Animation! 🎬→🦴→🎨

