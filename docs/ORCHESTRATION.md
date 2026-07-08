# SWIFT ↔ ANVIL Orchestration Contract

**Status:** Authoritative contract for external orchestrators (ANVIL — "Regisseur der
Generatoren") that drive SWIFT as a generator node.

This document is derived directly from the implementation in `main.py` (CLI),
`core/renderer.py` + `core/exporter.py` (artifacts), and `core/sprite_sheet.py`
(manifest schema). It intentionally does **not** invent flags that do not exist in
`main.py`. Where the existing README example disagrees with the actual CLI, this
document wins — see [Discrepancies with README](#discrepancies-with-readme).

SWIFT's role in the ecosystem: it is the **Character-/Actor-Production node**. It
consumes 3D character models (FBX) and produces animated sprite sheets (PNG) plus
machine-readable manifests (JSON) that SHADED consumes via
`window.SHADED.addActor({ image, manifest, ... })`. SWIFT does **not** mutate world
state — it is the pure presentation node for figures (Invariante 2 / Material Truth).

---

## 1. Invocation & exit codes

```bash
python main.py <subcommand> [options]
```

| Condition | Exit code | Notes |
|-----------|-----------|-------|
| No subcommand given | `0` | Prints help to stdout, exits 0. |
| Success | `0` | Processed without raising. |
| Missing required arg / argparse error | `2` | Standard argparse behavior. |
| Missing input (file/value) | `2` | Explicit `InputMissingError`: model FBX, video, sprite-sheet image, manifest, or required `--anim`/`--frame`/API-key missing. |
| External tool missing | `3` | `ToolMissingError`: Blender unavailable for `render`, PySide6 unavailable for `gui`. |
| Generic failure | `1` | Any other runtime error (tracker/render failure, unhandled exception, etc.). |

**Rule for ANVIL:** trust the exit code, not the textual output. `0` == success,
non-zero == failure. Retry/abort accordingly.

### stdout / stderr convention

There are two output modes:

- **Default (human mode):** all human-readable status/progress text is written to
  **stdout**; error/diagnostic lines are written to **stderr** (prefixed `ERROR:`).
- **Machine-readable mode (`--json` / `--json-summary`):** on success a **single**
  JSON object is written to **stdout** (`status:"success"` + command-specific keys,
  see [§2](#2-commands)). All progress/diagnostic text is redirected to **stderr**. On
  failure a `{"status":"error","error":<msg>}` object is written to **stderr** and the
  process exits with the code above (2 missing input, 3 tool missing, 1 generic).

```bash
# Success → stdout carries ONLY the JSON summary; diagnostics on stderr.
python main.py spritesheet list sheet.png --manifest m.json --json
#   stdout: {"status":"success","command":"spritesheet","action":"list",...}
#   stderr: (progress/summary lines)

# Failure → structured error on stderr, non-zero exit.
python main.py render --model missing.fbx --json
#   stderr: {"status":"error","error":"Model FBX not found: missing.fbx"}
#   exit:   2
```

> **Implication for ANVIL:** in machine-readable mode, branch on the exit code AND
> parse stdout (success) or stderr (failure) for the structured JSON. In human mode,
> rely solely on the exit code.

Output artifacts are produced as **files on disk**, not printed to stdout. In human
mode, stdout additionally carries `Done: <path>` style summaries for convenience; in
`--json` mode those are suppressed from stdout.

---

## 2.0 Machine-readable summary (`--json` / `--json-summary`)

Every subcommand accepts `--json` (alias `--json-summary`). When set:

- **Success** → exactly one JSON object is printed to **stdout** and the process
  exits `0`. All progress/diagnostic text is routed to **stderr**.
- **Failure** → `{"status":"error","error":<msg>}` is printed to **stderr** and the
  process exits with the code in [§1](#1-invocation--exit-codes) (`2` missing input,
  `3` tool missing, `1` generic). **Nothing** is written to stdout on failure.

The success object always contains:

```json
{
  "status": "success",
  "command": "<subcommand>"
}
```

plus command-specific keys. The `render` and `spritesheet` summaries carry the
orchestration-relevant fields:

| Key | Type | Present for | Meaning |
|-----|------|-------------|---------|
| `artifacts` | `[{type, path}]` | all | Output files produced (e.g. `sprite_sheet`, `manifest`, `depth_sheet`, `variant_sheet`, `world_state_sheet`, `bvh`, `gif`, `frame`). |
| `sheet_path` | string \| null | render, spritesheet, video2sprite | Primary sheet/image path. |
| `manifest_path` | string \| null | render, spritesheet | Manifest JSON path (null if none). |
| `depth_path` | string \| null | render | Depth sheet path (only with `--depth-pass`). |
| `world_states` | `[string]` | render | World-state names requested via `--world-states`. |
| `fps` | int \| null | render, spritesheet, mocap, video2sprite | Playback fps. |
| `frame_count` | int \| null | render, spritesheet, mocap, video2sprite | Number of frames. |
| `animation_names` | `[string]` | render, spritesheet | Animation keys in the manifest. |
| `mapping_version` | string \| null | render, spritesheet | `mappingVersion` from the manifest. |

**Example — `render` (success):**

```json
{
  "status": "success",
  "command": "render",
  "artifacts": [
    {"type": "sprite_sheet", "path": "/out/hero.png"},
    {"type": "manifest",     "path": "/out/hero_manifest.json"},
    {"type": "depth_sheet",  "path": "/out/hero_depth.png"}
  ],
  "manifest_path": "/out/hero_manifest.json",
  "sheet_path": "/out/hero.png",
  "depth_path": "/out/hero_depth.png",
  "world_states": ["dust", "aging"],
  "fps": 12,
  "frame_count": 24,
  "animation_names": ["walk"],
  "mapping_version": "1.4.0"
}
```

**Example — `render` (failure, Blender missing):**

```json
{"status": "error", "error": "Blender not available: <version string>"}
```
(exit code `3`, written to stderr.)

> **Determinism note:** in `--json` mode stdout contains *only* the single summary
> object — no progress lines, no `Done:` text. ANVIL may parse stdout directly with a
> strict JSON decoder.

## 2. Commands

### 2.1 `render` — FBX → sprite sheet (+ manifest, optional depth/variants)

Renders a character FBX (optionally with an animation FBX) to a sprite sheet. Always
emits a manifest when `--format sprite_sheet` (the default). Supports optional
procedural skeleton generation, a depth pass, palette variants, and SHADED
world-state variants.

```
python main.py render \
  --model character.fbx \
  [--anim animation.fbx] \
  [--output OUTPUT.png] \
  [--format {sprite_sheet|gif|frames_json}] \
  [--width W] [--height H] [--fps N] \
  [--camera {front|side|three-quarter}] \
  [--pixel-size N] \
  [--blender PATH] \
  [--anim-name NAME] \
  [--skeleton-generator] [--height-cm CM] [--weight-kg KG] [--with-ik] [--mesh-bodies] \
  [--depth-pass] [--normal-pass] [--emissive-pass] \
  [--variants "red,green,gold"] \
  [--world-states "dust,aging,heat"]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `--model` | **yes** | — | Character FBX path. |
| `--anim` | no | — | Animation FBX path. If omitted, a built-in animation is used. |
| `--output` | no | `<frames_dir>/output` | Output file path **stem**. `.png` / `_manifest.json` / `_depth.png` / `_normal.png` / `_emissive.png` are appended. |
| `--format` | no | `sprite_sheet` | `sprite_sheet` (PNG+JSON manifest), `gif`, or `frames_json`. |
| `--width` | no | `64` | Frame width in px. |
| `--height` | no | `64` | Frame height in px. |
| `--fps` | no | `12` | Animation fps. |
| `--camera` | no | `front` | Camera angle: `front` \| `side` \| `three-quarter`. |
| `--pixel-size` | no | `4` | Pixelation size for the render style. |
| `--blender` | no | auto | Path to Blender executable. |
| `--anim-name` | no | anim/model basename | Animation key written into the manifest. |
| `--skeleton-generator` | no | off | Generate a procedural skeleton from the params below. |
| `--height-cm` | no | `170.0` | Character height (scaling). |
| `--weight-kg` | no | `70.0` | Character weight. |
| `--with-ik` | no | off | Apply 2-bone IK chains to limbs. |
| `--mesh-bodies` | no | off | Generate capsule mesh bodies per bone. |
| `--depth-pass` | no | off | Enable Z-buffer depth pass (8-bit grayscale PNG). |
| `--normal-pass` | no | off | Enable normal-map pass (RGB PNG). Adds `normalImage`/`normalSourceImage`/`normalFrameRects` to the manifest. |
| `--emissive-pass` | no | off | Enable emissive pass (emission-only RGB PNG). Adds `emissiveImage`/`emissiveSourceImage`/`emissiveFrameRects` to the manifest. |
| `--variants` | no | — | Comma-separated palette variants. Two forms: named presets (`red`,`green`,`purple`,`gold`) or custom hex maps `name=#Src:Dst` (multiple pairs with `;`); runtime LUT pass, no re-render. |
| `--world-states` | no | — | Comma-separated SHADED world states (e.g. `dust,aging,heat`). |

**Failure modes:** `sys.exit(3)` (`ToolMissingError`) if Blender is unavailable after
`renderer.check()`; `sys.exit(2)` (`InputMissingError`) if `--model` FBX does not
exist; otherwise non-zero on unhandled render error (`sys.exit(1)`).

**Machine-readable mode:** pass `--json` / `--json-summary` to emit the summary in
[§2.0](#20-machine-readable-summary---json----json-summary) (artifacts, sheet/manifest/
depth paths, `world_states`, `fps`, `frame_count`, `animation_names`, `mapping_version`)
to stdout; all progress goes to stderr.

**Output artifacts:** see [§3.1](#31-render-artifacts).

> Note: `--skeleton-generator` may also export an FBX (`--model` becomes the skeleton
> output if `export_fbx` is implied). The generated skeleton can then be re-fed as
> `--model`. ANVIL should treat `--skeleton-generator` as a pre-pass that yields a new
> FBX to render.

---

### 2.2 `analyze` — reference sheet → StyleParams

Extracts style parameters from an existing reference sheet via Claude Vision (Anthropic).

```
python main.py analyze <sheet> [--api-key KEY]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `sheet` (positional) | **yes** | — | Path to reference sheet image. |
| `--api-key` | no | `$ANTHROPIC_API_KEY` | Anthropic API key. |

**Failure modes:** `sys.exit(2)` (`InputMissingError`) if no API key is available (env
or flag); this is a *missing input* condition, not a generic error. On success prints
extracted `Style parameters` (size, fps, camera, pixel size, palette hint, exaggeration)
to stdout and exits `0`.

**Output:** this command writes **no artifact file**. Results are printed as text to
stdout. ANVIL can parse the printed lines, or (recommended) feed the same sheet
through its own analysis. See [Future contract additions](#6-future-contract-additions).

---

### 2.3 `mocap` — video → BVH

Tracks a video with MediaPipe and exports a BVH motion-capture file.

```
python main.py mocap <video> [--output OUT.bvh]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `video` (positional) | **yes** | — | Input video file. |
| `--output` | no | `<video>.bvh` | Output BVH path. |

**Failure modes:** `sys.exit(1)` if `result.success` is false (prints `ERROR: <msg>`).
On success prints `Done: <out> (<frames> frames at <fps>fps)` and exits `0`.

**Output artifact:** a single `.bvh` file.

---

### 2.4 `video2sprite` — video → pixel-art sheet

Extracts frames from a video and pixelizes them into a sprite sheet (or GIF / frames).

```
python main.py video2sprite <video> \
  [--output OUT] [--format {sprite_sheet|gif|frames}] \
  [--width W] [--height H] [--colors N] [--keyframes]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `video` (positional) | **yes** | — | Input video file. |
| `--output` | no | `<video>_sprites.png` | Output path. |
| `--format` | no | `sprite_sheet` | `sprite_sheet` (PNG), `gif`, or `frames` (frames JSON dir). |
| `--width` | no | `64` | Target frame width. |
| `--height` | no | `64` | Target frame height. |
| `--colors` | no | `16` | Palette colors for pixelization. |
| `--keyframes` | no | off | Extract keyframes only. |

**Failure modes:** `sys.exit(1)` if frame extraction fails. On success prints
`Done: <out>` and exits `0`.

**Output artifact:** a PNG sheet (default), a GIF (`--format gif`), or a frames-JSON
directory (`--format frames`). No manifest is emitted by this command.

---

### 2.5 `spritesheet` — inspect / re-export an existing sheet + manifest

Operates on an **already produced** sprite sheet and its manifest. Three actions:

```
python main.py spritesheet list   <image> --manifest M.json
python main.py spritesheet export <image> --manifest M.json --anim NAME [--format {sprite_sheet|gif}] [--output OUT]
python main.py spritesheet extract <image> --manifest M.json --frame FID [--output OUT.png]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `action` (positional) | **yes** | — | `list` \| `export` \| `extract`. |
| `image` (positional) | **yes** | — | Sprite sheet PNG path. |
| `--manifest` | **yes** | — | Manifest JSON path. |
| `--anim` | required for `export` | — | Animation name to export. |
| `--frame` | required for `extract` | — | Frame ID to extract. |
| `--format` | no (`export`) | `gif` | `sprite_sheet` or `gif`. |
| `--output` | no | derived | Output path. |

**Failure modes:** `sys.exit(2)` (`InputMissingError`) if `--anim` missing for
`export`, `--frame` missing for `extract`, the sheet image is missing, or the manifest
is missing. On success prints a summary and exits `0`.

**Machine-readable mode:** pass `--json` / `--json-summary` to emit the success summary
(`artifacts`, `sheet_path`, `manifest_path`, `mapping_version`, `animation_names`,
`frame_count`, `fps`) to stdout instead of the human summary.

**Output artifacts:**
- `list` → prints animation/frame summary to stdout (no file).
- `export` → a GIF (`--format gif`, default) or a new sprite sheet PNG.
- `extract` → a single PNG frame.

---

## 3. Output artifacts per command

Artifacts are files on disk. The `--output` argument is a **path stem** for `render`
(except where noted); extensions are added by SWIFT.

### 3.1 `render` artifacts

Given `--output path/to/hero` and `--format sprite_sheet`:

| File | Produced when | Description |
|------|---------------|-------------|
| `path/to/hero.png` | always (sprite_sheet) | RGBA sprite sheet. |
| `path/to/hero_manifest.json` | always (sprite_sheet) | Manifest v1.4.0 (see §4). |
| `path/to/hero_depth.png` | `--depth-pass` | 8-bit grayscale depth sheet (same frame layout as color). |
| `path/to/hero_normal.png` | `--normal-pass` | RGB normal-map sheet (same frame layout as color). |
| `path/to/hero_emissive.png` | `--emissive-pass` | RGB emissive (emission-only) sheet (same frame layout as color). |
| `path/to/hero_<variant>.png` | `--variants` | Palette-swapped variant sheets. |
| `path/to/hero_<state>.png` | `--world-states` | SHADED world-state variant sheets. |

If `--output` is omitted, artifacts land in the temp render dir as
`<frames_dir>/output.png`, `<frames_dir>/output_manifest.json`, etc. **ANVIL should
always pass `--output` with an absolute, known path** so it can locate artifacts
deterministically.

For `--format gif`, the single artifact is `path/to/hero.gif` (no manifest). For
`--format frames_json`, the artifact is `path/to/hero_frames` (frames + JSON dir).

The manifest is **always** written for `sprite_sheet`; `--variants` and
`--world-states` append `variants` and `worldStates` entries to that same manifest
file in place.

### 3.2 `analyze` artifacts

None (text to stdout only).

### 3.3 `mocap` artifacts

| File | Description |
|------|-------------|
| `<out>.bvh` (default `<video>.bvh`) | Motion-capture skeleton animation. |

### 3.4 `video2sprite` artifacts

| File | Produced when | Description |
|------|---------------|-------------|
| `<out>.png` (default `<video>_sprites.png`) | `sprite_sheet` | Pixel-art sheet. |
| `<out>.gif` | `--format gif` | Animated GIF. |
| `<out>_frames/` | `--format frames` | Frames + JSON. |

No manifest is produced. If ANVIL needs a SHADED-consumable manifest from a
`video2sprite` sheet, it must run `spritesheet` to inspect, or construct one.

---

## 4. Manifest JSON schema (v1.4.0)

SWIFT emits manifests consumable by `core.sprite_sheet.SpriteSheetManifest` and by
SHADED's `addActor()`. The authoritative writer is `core/exporter.export_manifest()`.

**Full example (sprite_sheet + depth + world states):**

```json
{
  "mappingVersion": "1.4.0",
  "appliesTo": ["hero_manifest"],
  "sourceImage": { "w": 512, "h": 256 },
  "frameRects": {
    "F01": { "x": 0,   "y": 0, "w": 128, "h": 256 },
    "F02": { "x": 128, "y": 0, "w": 128, "h": 256 }
  },
  "frames": [
    { "id": "F01", "row": 1, "col": 1, "key": "F01" },
    { "id": "F02", "row": 1, "col": 2, "key": "F02" }
  ],
  "animations": {
    "walk": { "frames": ["F01", "F02"], "fps": 12, "loop": true }
  },
   "depthImage": "hero_depth.png",
   "depthSourceImage": { "w": 512, "h": 256 },
   "depthFrameRects": {
     "F01": { "x": 0,   "y": 0, "w": 128, "h": 256 },
     "F02": { "x": 128, "y": 0, "w": 128, "h": 256 }
   },
   "normalImage": "hero_normal.png",
   "normalSourceImage": { "w": 512, "h": 256 },
   "normalFrameRects": {
     "F01": { "x": 0,   "y": 0, "w": 128, "h": 256 },
     "F02": { "x": 128, "y": 0, "w": 128, "h": 256 }
   },
   "emissiveImage": "hero_emissive.png",
   "emissiveSourceImage": { "w": 512, "h": 256 },
   "emissiveFrameRects": {
     "F01": { "x": 0,   "y": 0, "w": 128, "h": 256 },
     "F02": { "x": 128, "y": 0, "w": 128, "h": 256 }
   },
   "variants": [
    { "name": "red",    "path": "hero_red.png" },
    { "name": "green",  "path": "hero_green.png" }
  ],
  "worldStates": {
    "dust":  { "name": "dust",  "transform": "dust",  "intensity": 0.5, "variant_path": "hero_dust.png" },
    "aging": { "name": "aging", "transform": "aging", "intensity": 0.7, "variant_path": "hero_aging.png" }
  }
}
```

### Field reference

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `mappingVersion` | string | yes | `"1.4.0"`. Bump on breaking schema changes. |
| `appliesTo` | string[] | yes | Set to `[<manifest-stem>]`; identifies the sheet this manifest applies to. |
| `sourceImage` | `{w,h}` | yes | Pixel dimensions of the **color** sheet. Used to scale rects for @2x exports. |
| `frameRects` | map id→`{x,y,w,h}` | yes | **Object form** `{x,y,w,h}` (not an array). Authoritative frame layout. |
| `frames` | array | yes | `[{id, row, col, key}]`. `key` is a semantic alias; defaults to `id`. |
| `animations` | map name→`{frames,fps,loop}` | yes | Ordered frame-id list + playback. |
| `depthImage` | string | optional | Basename of the depth sheet PNG (present iff `--depth-pass`). |
| `depthSourceImage` | `{w,h}` | optional | Pixel dimensions of the depth sheet. |
| `depthFrameRects` | map id→`{x,y,w,h}` | optional | Same frame ids as `frameRects`; object form. |
| `normalImage` | string | optional | Basename of the normal-map sheet PNG (present iff `--normal-pass`). |
| `normalSourceImage` | `{w,h}` | optional | Pixel dimensions of the normal-map sheet. |
| `normalFrameRects` | map id→`{x,y,w,h}` | optional | Same frame ids as `frameRects`; object form. |
| `emissiveImage` | string | optional | Basename of the emissive sheet PNG (present iff `--emissive-pass`). |
| `emissiveSourceImage` | `{w,h}` | optional | Pixel dimensions of the emissive sheet. |
| `emissiveFrameRects` | map id→`{x,y,w,h}` | optional | Same frame ids as `frameRects`; object form. |
| `variants` | array | optional | `[{name, path}]` palette variants (from `--variants`). |
| `worldStates` | map name→`WorldStateRef` | optional | SHADED world-state hooks (from `--world-states`). See below. |

> **Rect encoding is object form, not array.** SWIFT writes `{"x":..,"y":..,"w":..,"h":..}`
> and `core.sprite_sheet.SpriteSheetManifest` parses `r["x"]`/`r["y"]`/… — an array
> `[x,y,w,h]` will fail to load. (The README's array example is inaccurate; this
> document is authoritative.)

### `worldStates` field (SHADED world-state hooks)

`worldStates` is an **additive, optional** field mapping a world-state name (e.g.
`"dust"`, `"aging"`, `"heat"`) to a descriptor. It is produced by `render --world-states`
and written by `core/exporter.export_manifest(..., world_states=...)`. The Python
attribute is `SpriteSheetManifest.world_states` (`core/sprite_sheet.py`); the JSON key
is `worldStates`. Each entry serializes via `WorldStateRef.to_dict()`:

```json
"<stateName>": {
  "name": "<stateName>",
  "transform": "<transformName>",   // procedural transform (e.g. "dust"); falls back to legacy "palette"
  "intensity": 0.5,                  // scalar intensity in [0, 1]
  "variant_path": "<stateName>.png" // basename of the generated variant PNG
}
```

SHADED uses `worldStates` to parameterize the actor by explicit world states without
SWIFT re-rendering. If a state name is unknown to the palette table, SWIFT prints a
warning and skips it (the manifest entry is simply omitted).

> **Serialization note:** `WorldStateRef.to_dict()` emits `transform` (not `palette`)
> plus a **scalar** `intensity` (not a `[min, max]` range) and the generated
> `variant_path`. The legacy form (`palette` key + `intensity` range) still loads
> (backward compatible) but is never produced by the current CLI. This document is
> authoritative for what `render --world-states` actually writes.

---

## 5. Passing the manifest to SHADED via `addActor()`

SWIFT's contract boundary ends at producing the PNG sheet + `_manifest.json`. ANVIL is
responsible for handing both to SHADED:

```js
// ANVIL (browser/JS context) loads the manifest SWIFT wrote and passes it to SHADED.
const manifest = await fetch('hero_manifest.json').then(r => r.json());

const actor = await window.SHADED.addActor({
  image: 'hero.png',        // sprite sheet PNG (path/URL SWIFT produced)
  manifest: manifest,       // parsed JSON object SWIFT wrote
  x: 0.5, y: 0.5,           // scene position
  scale: 1.0,               // scaling
  anim: 'walk',             // animation key from manifest.animations
  depthLayer: 'mid'         // depth layer (front|mid|back); uses depthImage if present
});
```

Contract points ANVIL must honor:

1. **`image`** — the sprite sheet PNG path/URL SWIFT emitted (e.g. `hero.png`).
2. **`manifest`** — the **parsed JSON object** (or a URL SHADED will fetch & parse) that
   SWIFT wrote to `<output>_manifest.json`. It must match §4 exactly.
3. **`anim`** — a key present in `manifest.animations`. SWIFT guarantees at least one
   animation (named via `--anim-name`, defaulting to the FBX basename).
4. **`depthLayer`** — only meaningful when `manifest.depthImage` is present (i.e. SWIFT
   was run with `--depth-pass`). SHADED then uses `depthImage` + `depthFrameRects` for
   spatial layering.
5. **Variant / world-state selection** — if ANVIL wants a palette variant or world-state
   look, it should point `image` at the variant/world-state PNG SWIFT produced
   (`hero_red.png`, `hero_dust.png`, …) while keeping the same `manifest` (frame layout
   is identical across variants).

> **Invariante 2 (Material Truth):** the actor is purely optical. It must not influence
> SHADED's material classification or physics. SWIFT sets no world state; it only
> provides presentation. ANVIL must not use SWIFT outputs to mutate world state.

---

## 6. Future contract additions

Implemented items are marked ✅. Remaining items are **proposed**, not yet implemented.

1. ✅ **Errors to stderr + machine-readable summary.** All subcommands accept
   `--json` / `--json-summary`. In that mode progress/diagnostic text goes to stderr
   and a single JSON object is emitted to stdout on success, or
   `{"status":"error","error":<msg>}` to stderr on failure (see [§2.0](#20-machine-readable-summary---json----json-summary)).
   In human mode, `ERROR:` lines are also routed to stderr.
2. ✅ **Stable machine-readable success summary.** Implemented as documented in
   [§2.0](#20-machine-readable-summary---json----json-summary) with `artifacts`,
   `sheet_path`, `manifest_path`, `depth_path`, `world_states`, `fps`,
   `frame_count`, `animation_names`, `mapping_version`.
3. ✅ **`analyze` structured output.** `analyze --json` emits the `StyleParams`
   object under the `style` key of the success summary (requires `ANTHROPIC_API_KEY`).
4. **Manifest for `video2sprite` / `gif`.** Only `render` (sprite_sheet) emits a SHADED
   manifest. A flag to emit a manifest for `video2sprite` output would make those sheets
   directly `addActor`-consumable.
5. **`--output` as directory.** Today `render --output` is a file stem; artifacts are
   derived by suffix. A directory mode would group sheet/manifest/depth/variants.

---

## Discrepancies with README

The repo `README.md` predates this contract and contains inaccuracies. This document is
authoritative for the CLI:

- README shows `render ... --export-manifest output_manifest.json`. **No such flag
  exists.** `render` always writes `<output>_manifest.json` (for `sprite_sheet`); there
  is no `--export-manifest` option.
- README shows `frameRects` values as arrays `[x,y,w,h]`. **Actual format is the object
  `{x,y,w,h}`** (see §4). Array form will fail to load in `SpriteSheetManifest`.
- README implies `--output` is a directory. **It is a file stem**; extensions are
  appended by SWIFT.
- README's SHADED example passes `manifest: 'output_manifest.json'` (a URL string). Both
  a URL string and a parsed object are acceptable to SHADED; this contract recommends
  passing the parsed object (§5).

See `docs/ECOSYSTEM.md` for SWIFT's role among the six ecosystem actors.
