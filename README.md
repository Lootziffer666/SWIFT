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
