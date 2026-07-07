# Critter Crosser – Engine & Studio Documentation

Diese Dokumentation beschreibt die Implementierung der im technischen
Konzept ("Die Entwicklungs-Pipeline von Critter Crosser") beschriebenen Systeme
als Python-Paket `core/critter/` innerhalb von **SWIFT**. Sie deckt Architektur,
jede Subsystem-Gruppe, die öffentliche API, die Studio-GUI und die
CLI-/Test-Integration ab.

---

## 1. Überblick & Architektur

SWIFT ist eine Pipeline, die Video- und 3D-Charakter-Captures in Pixel-Art-
Sprite-Sheets verwandelt (Blender-Bridge, KI-Style-Analyse, Mocap). Das
`core/critter/`-Paket ist eine **prozedurale Kreatur-Engine**, die exakt die im
Konzept geforderten mathematischen Systeme bereitstellt und sich nahtlos in
SWIFTs `core/`-Layout einfügt.

**Schichten:**

```
core/critter/
  geometry.py      Vektormathematik + isometrische (Fake-3D) Projektion
  sdf.py           Signed Distance Fields + Bounding-Box-Rasterizer
  ik.py            Inverse Kinematik (Kosinussatz, FABRIK, Z-Bend, Feder)
  shaders.py       Perlin-Noise, Palette-Swap, Partikel, Transparenz
  flow_field.py    Flow-Field-Pathfinding + NPC-Low-Power
  evolution.py     Skelett-Morphing + Zucht
  input.py         Twin-Stick-Controller
  scheduling.py    NPC-Scheduling aus Textdateien
  engine.py        Critter + Engine-Fassade
  studio.py        StudioModel (State + Render-Daten für die GUI)

gui/
  app.py           StudioWindow + Einstiegspunkt
  viewport.py      Viewport / FlowView / PerlinView / StickView
  panels.py        Steuer-Panels (Evolution, IK, Flow, Palette, Perlin, Stick)
```

**Kernprinzip:** Alle Algorithmen sind reine Python-Funktionen/Klassen ohne
GUI-Abhängigkeit. Die GUI (`gui/`) ist nur ein dünner View-Layer über den
`StudioModel`, das sämtlichen manipulierbaren Zustand hält und eine
`render()`-Methode zurückgibt, die schlichte, serialisierbare Zeichendaten in
Bildschirmkoordinaten liefert. Dadurch ist die gesamte Engine logik-getestet
headless lauffähig (`tests/test_critter_*.py`).

---

## 2. Fake-3D & SDFs (`geometry.py`, `sdf.py`)

### 2.1 Isometrische Projektion (Snyder-Ansatz)

Standard-3D-Perspektivmatrizen versagen unter der fixen isometrischen Kamera.
Wir adaptieren Snyder's planare Kartenprojektion: eine orthografische 2:1-
Isometrie ohne Perspective-Divide.

```python
from core.critter.geometry import Vec3, Vec2, IsometricProjection

proj = IsometricProjection(scale=32.0, vertical_squash=0.5, origin=Vec2(0, 0))
screen = proj.project(Vec3(3, 1.5, -2))          # Welt -> Screen
world  = proj.unproject(screen, height=1.5)       # Screen -> Welt (Invers)
```

`project` bildet `(x−z, (x+z)·squash − y)` ab; `unproject` rekonstruiert den
Bodenpunkt bei gegebener Höhe.

### 2.2 Signed Distance Fields

Organische Kreaturen werden statt durch Polygon-Meshes durch SDFs beschrieben.
Der Shader (hier CPU-Referenz) evaluiert pro Pixel eine Distanzfunktion; eine
Fläche liegt bei Distanz 0. Vorteile aus dem Konzept: keine Texture-Glitches,
kein "Pinching" bei Gelenk-Rotationen, plus "Jelly"-Effekte durch sinusoidale
Displacement und weiches Verschmelzen.

```python
from core.critter.sdf import (sdf_sphere, sdf_capsule, sdf_box,
                               sdf_union, sdf_smooth_union, sdf_sinusoidal_displace,
                               BoundingBox, SDFRenderer)

d = sdf_sphere(p, center=Vec3(0,0,0), radius=2.0)   # <0 innen, >0 außen
d = sdf_smooth_union(a, b, k=0.5)                    # "Jelly"-Blend
d = sdf_sinusoidal_displace(d, p, frequency=2.0, amplitude=0.2,
                            phase=0.0, direction=Vec3(0,1,0))
```

**Performance:** `SDFRenderer.rasterize(box, field, sample_step)` wertet `field`
ausschließlich innerhalb der `BoundingBox` der Kreatur aus – nie full-screen:

```python
renderer = SDFRenderer(proj)
grid = renderer.rasterize(BoundingBox(Vec2(-80,-80), Vec2(80,80)),
                          lambda q: sdf_sphere(q, Vec3(0,0,0), 2.0), sample_step=4.0)
mask = renderer.occupancy_mask(box, field)          # boolesches Innent/Mask
```

---

## 3. Prozedurale Animation & IK (`ik.py`)

Keine Keyframes – jedes Glied wird pro Frame mathematisch gelöst.

### 3.1 Zwei-Knochen (Kosinussatz)

Reptilien-Beine: geschlossene Lösung via Law of Cosines.

```python
from core.critter.ik import solve_two_bone_law_of_cosines
mid = solve_two_bone_law_of_cosines(root, target, l1=1.2, l2=1.2,
                                    bend_direction=Vec3(0,1,0))
# |mid-root| == l1, |mid-target| == l2; unerreichbare Ziele werden geklemmt.
```

### 3.2 Multi-Joint (FABRIK)

Flügel/Tentakel mit 5+ Gelenken. Vorwärts/Rückwärts-Reichweiten-IK, Root
bleibt verankert, Knochenlängen konstant.

```python
from core.critter.ik import BoneChain, fabrik_solve
chain = BoneChain(joints=[Vec3(0,0,0), Vec3(1,0,0), Vec3(2,0,0), Vec3(3,0,0)],
                  lengths=[1.0,1.0,1.0])
fabrik_solve(chain, Vec3(0,0,2.9), iterations=30)   # chain.joints mutiert
```

### 3.3 Z-Biegung (Säugetier-Galopp)

Generische IK biegt Beine salamander-artig. `ZBendConstraint.inject` führt
*jede Frame* einen Forward-Pull am ersten und Backward-Pull am zweiten Gelenk
durch, bevor der Solver läuft – erzwingt das Z-Muster.

```python
from core.critter.ik import ZBendConstraint
ZBendConstraint(forward_pull=0.3, backward_pull=0.3).inject(chain, motion=Vec3(1,0,0))
```

### 3.4 Wobbly Tower (Federphysik)

Rüssel/Schwänze: Punkt-Massen via Verlet + Distanz-Constraints, Basis
gepinnt, Trägheit entsteht natürlich.

```python
from core.critter.ik import WobblyTower
tower = WobblyTower.create(base=Vec3(0,0,0), segment_count=6, segment_length=0.6)
for _ in range(30):
    tower.step(dt=1/60.0, tip_target=Vec3(1,0,0))
tower.positions            # Liste[Vec3] der aktuellen Knoten
```

---

## 4. VFX & Shader (`shaders.py`)

~90 % der visuellen Komplexität kommen aus Perlin-Noise + GPU-Mathematik.

### 4.1 Perlin Noise

```python
from core.critter.shaders import PerlinNoise
n = PerlinNoise(seed=42)
n.scrolling(x, y, time)            # fließendes Wasser / Nebel / Wolken
n.distortion(x, y, time, amount)  # Elektrizität / Magie / Hitzeflimmern
n.stretched(x, y, time, scale)    # Wellen / organische Pulsation
```

### 4.2 Dynamische Farbgebung / Palette Swap

**Kritischer Bug-Hinweis aus dem Konzept ist implementiert:**
- Die Uniform heißt `palette`, **nicht** `"Sprite 0"` (Namenskonflikt mit
  Debug-Sprite → Farbstörungen/Stretching).
- RGB (0–255) **muss** in Shader-Floats (0.0–1.0) konvertiert werden, sonst
  Übersteuern auf rein Weiß.

```python
from core.critter.shaders import PaletteSwap, Color
pal = PaletteSwap([Color(0.9,0.2,0.2,1.0), Color(0.2,0.8,0.3,1.0)])
c = PaletteSwap.to_shader_color(255, 128, 0)   # -> Color(1.0, 0.502, 0.0, 1.0)
region_color = pal.resolve(region_id)          # Masken-Auflösung zur Laufzeit
```

### 4.3 GPU-Partikel

`ParticleSystem` ist ein Struct-of-Arrays (einmal allokiert), spiegelt die
GPU-Lösung (Mesh-Init beim Start, bis ~1 Mio. Partikel).

```python
from core.critter.shaders import ParticleSystem
ps = ParticleSystem(capacity=1_000_000)
ps.spawn(0, Vec3(0,0,0), Vec3(0,5,0), life=1.0)
ps.update(dt=1/60.0)            # O(alive), keine Reallokation
```

### 4.4 Single-Pass-Transparenz

Bei fixer Kamera reicht strikt back-to-front Sortierung (kein Multi-Pass):

```python
from core.critter.shaders import sort_back_to_front
ordered = sort_back_to_front([("near", Vec3(0,0,0)), ("far", Vec3(0,0,10))], proj)
# -> ["far", "near"]
```

---

## 5. KI & Pathfinding – Flow Fields (`flow_field.py`)

Bis zu Tausende NPCs statt per-Agent A*: ein Distanzfeld vom Ziel, dann ein
Vektorfeld (jede Kachel zeigt zum günstigsten Nachbarn). **1 Byte/Kachel.**

```python
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC

cfg = FlowFieldConfig(width=24, height=16, default_cost=1)
field = FlowField(cfg)
field.set_cost(5, 5, 100)          # "Street" teuer -> wird gemieden
field.set_blocked(6, 6, True)     # unpassierbar
field.compute([(23, 8)])          # Ziel(e)
d = field.direction_at(0, 0)      # Vec2 in Richtung des Feldes
field.memory_bytes()              # == width*height

npc = NPC(id=1, x=0, y=0, on_screen=False)
npc.update(field, speed=1.0, dt=1.0)
# off-screen -> LOW-POWER: keine Kollision, keine State-Machine.
```

**Tile Costs:** Sidewalk=1, Street=100 erzwingt natürliche Umwege über
Gehwege. **Low-Power-Mode:** Off-Screen-NPCs überspringen Kollisionsabfrage
und komplexe State-Machines.

---

## 6. Prozedurale Evolution & Zucht (`evolution.py`)

Transformation ist mathematische Interpolation von Skelett-Daten – jede
Zwischenstufe ist voll funktionsfähig.

```python
from core.critter.evolution import Skeleton, morph, breed

# Real-Time Morphing (LERP larva -> adult)
child = morph(larva, adult, t=0.5)     # t=0..1, alle Zwischenformen animierbar

# Breeding: Averaging + Clamping + Virtual Scaling + Mutation
kid = breed(parent_a, parent_b, mutation_rate=0.1, rng=random.Random(0))
```

- **Averaging & Clamping:** Gliedmaßenlängen gemittelt; Segment-/Augen-/Glied-
  zahlen auf die Spanne der Eltern *geclampt* (keine "Gen-Explosion" à 12 Beine).
- **Virtual Scaling:** Eltern vor dem Blend auf einheitliche virtuelle Länge
  gestreckt/gestaucht → keine Überhänge am Hinterteil.
- **Mutationen:** Dominanz + kleine Zufallsvariationen in den Skelett-Dimensionen.

---

## 7. Steuerung & Scheduling (`input.py`, `scheduling.py`)

### 7.1 Twin-Stick

D-Pad wurde durch Maus/Twin-Stick ersetzt: Blick- und Bewegungsrichtung
entkoppelt, sofortige Reaktion (kein Rotations-Lag), Side-Stepping möglich.

```python
from core.critter.input import TwinStickController
c = TwinStickController()
c.set_movement(0, 1)      # vorwärts
c.set_aim(1, 0)           # nach rechts schauen (entkoppelt)
v = c.velocity(speed=5.0) # sofortige Bewegung, kein Latenz
c.can_side_step()         # True wenn Bewegung ~senkrecht zur Blickrichtung
```

### 7.2 NPC-Scheduling

Tagesabläufe als menschenlesbare Textdateien (einfaches Modding):

```
# daily routine
08:00 wake home
12:00 eat market
18:00 sleep home
```

```python
from core.critter.scheduling import NPCSchedule
sched = NPCSchedule.from_file("npc.txt")
entry = sched.active_entry(hour=13, minute=30)   # -> eat/market
field = sched.route_to(npc, goal=(9,0), grid_w=10, grid_h=1)  # Flow-Field-Route
```

---

## 8. Engine-Fassade (`engine.py`)

`Critter` kapselt Skelett + SDF-Körperfeld; `Engine` tickt IK, Flow-Field-NPCs,
Scheduling und den Twin-Stick pro Frame.

```python
from core.critter.engine import Critter, Engine
crit = Critter("Tester", adult_skeleton)
field = crit.body_field()          # Callable[[Vec3], float] (SDF)
eng = Engine()
eng.add_critter_npc(npc, schedule)
eng.update_npcs(flow_field, speed=1.0, dt=1.0)
```

---

## 9. Studio GUI (`gui/`)

Interactive Studio (PySide6 – bereits in `requirements.txt`). Start:

```bash
python main.py gui
```

**Layout & Interaktion:**

| Bereich | Inhalt | Eingriff |
| ------ | ------ | -------- |
| Center Viewport | Kreaturen (SDF-Körper), IK-Kette, Wobbly-Tower | **Rote Handhabe ziehen** = IK-Endeffektor-Ziel |
| FlowView | 1-Byte/Kachel-Feld, NPC-Punkte, Ziel-Marker | **Linksklick** Ziel · **Shift** Street(100) · **Rechts** blockieren |
| PerlinView | animierte Noise-Vorschau | (Modus/Scale in Perlin-Panel) |
| StickView | Twin-Stick | **Linksziehen** Bewegung · **Rechtsziehen** Zielrichtung |
| Left Dock | Evolution & Breeding, IK | Morph-Slider, Züchten, Spawn, Solver, Z-Bend, Gelenk-Pulls |
| Right Dock (Tabs) | Flow / Palette / Perlin / Stick | Step, Play, **Palette live umfärben**, Noise-Modus/Scale, Readout |

Der Animations-Timer (33 ms) schaltet Play-Modi (Perlin/ Flow) und repaintet.

Die GUI ist ein reiner View über `StudioModel` (`core/critter/studio.py`),
welches allen Zustand hält und `render()` liefert. Logik ist headless testbar.

---

## 10. CLI (`main.py`)

```bash
# Prozedurale Engine-Demo (Morph, Breed, Flow-Field, IK)
python main.py critter --npcs 400 --grid 60 --steps 100 --evolution 0.5

# Interaktives Studio
python main.py gui
```

Bestehende SWIFT-Befehle (`render`, `analyze`, `mocap`, `video2sprite`,
`spritesheet`) bleiben unverändert.

---

## 11. Tests

```bash
pytest tests/test_critter_*.py -v
```

| Datei | Deckung |
| ------ | ------ |
| `test_critter_sdf.py` | Projektion Roundtrip, SDF-Primitive, Bounding-Box-Limit |
| `test_critter_ik.py` | Kosinussatz, FABRIK (Reach/Root/Längen), Z-Bend, Wobbly-Tower |
| `test_critter_shaders.py` | Perlin-Saat, Palette-Bugregeln (kein "Sprite 0", 0–255→float), Partikel, Transparenz |
| `test_critter_flow_field.py` | Flussrichtung, Blocking, Tile-Cost-Bias, 1-Byte/Kachel, Low-Power |
| `test_critter_evolution.py` | Morph-Monotonie, Breed-Averaging, Clamping, Virtual-Scaling, Mutation |
| `test_critter_input_scheduling.py` | Twin-Stick-Entkopplung, Side-Step, Schedule-Parsing/Aktivität, Routing |
| `test_critter_studio.py` | StudioModel-State, Render-Struktur, GUI-Import (skip ohne PySide6) |

---

## 12. Erweitern

- **Neue SDF-Form:** Funktion in `sdf.py` hinzufügen (Signatur `f(Vec3)->float`),
  in `SDFRenderer`/GUI nutzbar.
- **Neuer IK-Solver:** `BoneChain` + Funktion in `ik.py`; in `StudioModel.solve_ik`
  und `IKPanel` einbinden.
- **Mehr VFX:** `PerlinNoise`-Modi erweitern; `PaletteSwap` um weitere Masken.
- **Eigene Kreatur:** `Skeleton(...)` bauen, via `StudioModel.spawn_random`/
  `add_critter` einhängen.

Alle Erweiterungen sind rein funktional und sofort headless testbar.
