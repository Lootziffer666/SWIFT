# SWIFT — Sprite Animation AI Workflow ("Get schwifty")

SWIFT turns video and 3D character captures into pixel-art sprite sheets, with
AI style analysis, a Blender bridge, and motion-capture support.

See `README.txt` for asset/license notes (Universal Animation Library models by
@Quaternius, CC0).

## Critter Crosser engine

`core/critter/` is a procedural creature engine that maps onto SWIFT's
pipeline. It implements the systems described in the Critter Crosser technical
concept:

| System | Module | Highlights |
| ------ | ------ | ---------- |
| Fake-3D + SDFs | `geometry.py`, `sdf.py` | Isometric (Snyder-style) projection; signed-distance-field creatures with `sinusoidal_displace` + smooth `jelly` blending, evaluated only inside each monster's bounding box |
| Procedural IK | `ik.py` | Law-of-cosines 2-bone solver, `FABRIK` for 5+ joints, `ZBendConstraint` for mammal gallop, `WobblyTower` spring physics for trunks/tails |
| VFX / shaders | `shaders.py` | Perlin noise (scroll/distort/stretch), runtime `PaletteSwap` (no `"Sprite 0"` name, 0–255→0.0–1.0 floats), GPU-friendly `ParticleSystem`, back-to-front transparency sort |
| Flow-field AI | `flow_field.py` | 1-byte/tile distance + vector fields, tile-cost routing (sidewalk 1 vs street 100), low-power off-screen NPCs |
| Evolution / breeding | `evolution.py` | `morph()` LERP larva→adult, `breed()` averaging + clamping + virtual scaling + mutation |
| Input / scheduling | `input.py`, `scheduling.py` | Twin-stick controller (decoupled look/move), human-readable NPC schedules routed via flow fields |

### Run the demo

```bash
python main.py critter --npcs 400 --grid 60 --steps 100
```

### Tests

```bash
pytest tests/test_critter_*.py -v
```

## Studio GUI

A live, interactive studio (PySide6 — already in `requirements.txt`) lets you
*see what happens and intervene* in real time:

```bash
python main.py gui
```

Layout:
- **Center viewport** — creatures (SDF body spheres), the IK limb chain, and the wobbly-tower trunk. **Drag the red handle** to move the IK end-effector target.
- **Flow Field view** — 1-byte/tile field with NPC dots and the goal marker. **Left-click** sets the goal, **Shift-click** paints a costly "street" (cost 100), **Right-click** toggles a blocked tile.
- **Perlin view** — animated noise preview (scroll / distort / stretch).
- **Twin-stick view** — **left-drag** = movement, **right-drag** = aim; shows the side-step indicator.
- **Left dock** — Evolution & Breeding (morph slider, breed, spawn random) and IK (solver, Z-bend toggles, joint pulls).
- **Right dock tabs** — Flow (step / play), Palette Swap (recolor region masks live), Perlin (mode/scale/animate), Twin-Stick readout.

The GUI is a thin view over `StudioModel` (`core/critter/studio.py`), which holds all state and produces plain render data — so the engine logic stays testable headlessly (`tests/test_critter_studio.py`).
