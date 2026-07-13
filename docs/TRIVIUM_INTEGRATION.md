# SWIFT ↔ TRIVIUM Integration Contract

## Role

TRIVIUM plans transformations. SWIFT is the **material workshop** that executes visual and structural transformations using existing tools wherever possible.

SWIFT should not become a monolithic converter. It should expose small, composable operations with explicit inputs, outputs and evidence.

## Supported transformation families

- 3D model or animated scene → directional frames / sprite sheets
- sprite or layered image → mesh, voxel, SDF or other spatial realization
- rig and animation normalization / baking / retarget preparation
- texture extraction, channel packing and PBR normalization
- scene or model rendering to 2D, 2.5D, depth, normal, emissive and masks
- atlas creation, trimming, segmentation and metadata generation
- geometry representation changes: mesh, voxel, SDF, tile, point cloud

## Job contract

```yaml
job:
  source:
    artifact: ...
    semantic_role: playable_character
  target:
    representation: sprite_sheet
    directions: 8
    animations: [idle, walk, interact]
  preserve:
    - silhouette
    - animation_timing
    - facing_readability
  may_drop:
    - facial_rig
    - cloth_simulation
  evidence:
    - output_manifest
    - frame_count
    - preview_render
```

Every operation must report:

- exact tool and version used
- source and output hashes
- transformed, preserved, approximated and lost properties
- generated manifests and preview evidence
- deterministic command/configuration where possible

## Tool composition

Prefer wrapping proven tools over reimplementing them. Candidate families documented in TRIVIUM include Blender headless pipelines, scene-to-sprite tools, shader converters, rig converters, terrain/voxel/SDF tools, atlas tools and engine import/export adapters.

SWIFT may provide glue scripts, presets and normalization layers. It should only implement a conversion algorithm itself when no suitable tool exists or existing tools cannot be safely automated.

## Field-first direction

SWIFT's morphing concept should generalize from pixels to coordinates and fields. A transformation may drive geometry, SDF, collision source data, masks and visible projections from one canonical deformation state. Visual-only deformation must be explicitly marked when collision or navigation do not follow.

## Boundaries

SWIFT does not:

- choose the game idea or asset role
- claim semantic equivalence without TRIVIUM contracts
- decide completion without CUE evidence
- own engine-specific final assembly

## Canonical references

- Tool candidates: https://github.com/Lootziffer666/TRIVIUM/blob/docs/semantic-realization-direction/docs/tool-candidate-catalog.md
- Realization contracts: https://github.com/Lootziffer666/TRIVIUM/blob/docs/semantic-realization-direction/docs/realization-contracts.md
- Engine interpreter: https://github.com/Lootziffer666/TRIVIUM/blob/docs/semantic-realization-direction/docs/engine-dolmetscher.md
