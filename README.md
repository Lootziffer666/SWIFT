# SWIFT

**Sprite-Werkzeug für Windy, Interactive, Frames, Tinting** – ein Python/Blender-CLI zur Generierung von animierten Pixel-Art-Sprite-Sheets aus FBX-Charaktermodellen.

## Übersicht

SWIFT rendert 3D-Charaktere in Blender headless zu animierten Sprite-Sheets (PNG) mit automatisch erzeugten **Manifesten** (JSON) für Frame-Layout und Animationen. Die erzeugten Sheets sind direkt kompatibel mit SHADED's Actor-System via `window.SHADED.addActor()`.

```bash
python main.py render \
  --model character.fbx \
  --anim idle \
  --format sprite_sheet \
  --export-manifest output_manifest.json
# Output: output.png (RGB), output_manifest.json (v1.4.0)
```

Das erzeugte Manifest kann sofort in SHADED geladen werden – keine weitere Konfiguration nötig.

## Installation

```bash
pip install -r requirements.txt
# Blender 3.x+ erforderlich (wird per subprocess aufgerufen)
apt-get install -y blender  # oder brew install blender (macOS)
```

## CLI-Verwendung

### Sprite-Sheet Export mit Manifest

```bash
python main.py render \
  --model path/to/character.fbx \
  --anim walk \
  --format sprite_sheet \
  --output output_dir/ \
  --export-manifest \
  --anim-name "walk"
```

**Parameter:**
- `--model`: FBX-Charakter-Datei
- `--anim`: Blender-Animations-Name (aus FBX extrahiert)
- `--format`: `sprite_sheet` (PNG + JSON Manifest)
- `--output`: Ausgabeverzeichnis
- `--export-manifest`: Manifest JSON automatisch erzeugen
- `--anim-name`: Name für den Animation-Key im Manifest (Default: Basis-Filename)

**Output:**
- `output.png`: RGB Sprite-Sheet (RGBA mit Transparenz)
- `output_manifest.json`: v1.4.0 Manifest mit Frame-Rects und Animationen

### Manifest-Schema (v1.4.0)

```json
{
  "mappingVersion": "1.4.0",
  "sourceImage": { "w": 512, "h": 256 },
  "frameRects": {
    "F01": [0, 0, 128, 256],
    "F02": [128, 0, 128, 256]
  },
  "frames": [
    { "id": "F01", "key": "walk_01" },
    { "id": "F02", "key": "walk_02" }
  ],
  "animations": {
    "walk": {
      "frames": ["F01", "F02"],
      "fps": 12,
      "loop": true
    }
  }
}
```

**Felder:**
- `mappingVersion`: Schema-Version (1.4.0 = mit Depth-Map Support)
- `sourceImage`: Sprite-Sheet Dimensionen (w, h)
- `frameRects`: Koordinaten jedes Frames im Sheet [x, y, w, h]
- `frames`: Frame-Metadaten mit eindeutigem ID + semantischem Key
- `animations`: Benannte Animations-Sequenzen mit FPS und Loop-Flag

**Phase B2 – Optional Depth-Map Support:**
```json
{
  ...
  "depthImage": "output_depth.png",
  "depthSourceImage": { "w": 512, "h": 256 },
  "depthFrameRects": {
    "F01": [0, 0, 128, 256],
    "F02": [128, 0, 128, 256]
  }
}
```

## SWIFT → SHADED Integration

Das erzeugte Manifest + Sprite-Sheet können direkt in SHADED geladen werden:

```html
<!-- index.html / Browser-Test -->
<script>
const actor = await SHADED.addActor({
  image: 'output.png',           // Sprite-Sheet
  manifest: 'output_manifest.json', // Auto-erzeugtes Manifest
  x: 0.5, y: 0.5,               // Szenen-Position
  scale: 1.0,                    // Skalierung
  anim: 'walk',                  // Animation-Name aus Manifest
  depthLayer: 'mid'              // Tiefenschicht (front/mid/back)
});
</script>
```

**Invariante 2 (Material Truth):** Actors sind rein optisch – sie beeinflussen nicht SHADED's Material-Klassifikation oder Physik-Simulation. Die Szenen-Analyse läuft allein auf dem Hintergrund-Bild.

## Architektur

### Core-Module

**`core/renderer.py`**
- `RenderJob`: Konfigurationsobjekt für einen Render-Auftrag
- `Renderer`: Hauptklasse für Blender-Headless-Rendering
- `render_and_export()`: Frames rendern + zu Sprite-Sheet packen

**`core/blender_bridge.py`**
- `BlenderBridge`: Schnittstelle zu Blender-Subprocess
- Lädt FBX, extrahiert Animationen, startet Render-Passes
- Gibt `RenderResult` mit Frame-Pfaden zurück

**`core/sprite_sheet.py`**
- `SpriteSheetManifest`: Dataclass für Manifest-Schema
- `PackedFrame`: Einzelner Frame mit Rects
- Packing-Logik: spalten-basiertes Layout (optimiert für viele Frames)

**`core/exporter.py`**
- `export_sprite_sheet()`: Frames zu PNG packen
- `export_manifest()`: JSON-Manifest schreiben
- `Exporter`: High-Level API für komplette Export-Pipelines

### Rendering-Pipeline

```
FBX-Datei
    ↓
BlenderBridge.render()
    ├─ Setup Szene + Armature
    ├─ Iterate Animations → Frames
    └─ RenderResult { frame_paths: [...], metadata }
    ↓
Exporter.to_sprite_sheet() + .to_manifest()
    ├─ PIL: Frames zu Sheet packen (spaltenweise)
    └─ JSON: Manifest mit frameRects, animations schreiben
    ↓
output.png + output_manifest.json
    ↓
SHADED: window.SHADED.addActor({ image, manifest, ... })
```

## Tests

```bash
# Unit-Tests (reine Logik, kein Blender)
pytest tests/test_sprite_sheet.py -v
pytest tests/test_exporter.py -v

# Manifest Round-Trip Test
pytest tests/test_exporter_manifest.py -v
# Lädt erzeugtes Manifest, validiert Struktur, parst zurück zu Python-Objekten
```

## Abhängigkeiten

| Paket | Zweck |
|-------|-------|
| `Pillow` | PNG-Verarbeitung (Sprite-Sheet Packing) |
| `Blender 3.x+` | Headless-Rendering via subprocess |
| `pytest` | Unit-Tests |

Blender wird NICHT als Python-Modul importiert, sondern via Subprocess aufgerufen (`blender --background --python ...`). Das erlaubt flexible Blender-Versionen und sichere Parallelisierung.

## Zukunfts-Erweiterungen (Phase 2+)

- **Depth-Rendering:** Blender Z-Buffer-Pass zu 8-bit Grayscale PNG (Phase B2)
- **Procedurale Skelette:** Parametrische Charakter-Generierung (IK, Proportionen)
- **Palette-Swapping:** Runtime-Farbvarianten ohne Neubau (schnelle Personalisierung)
- **Multi-Pass Rendering:** Separate Passes für Normal-Maps, Emissive (für erweiterte Visuals)

## Git & Branches

- Branch: `claude/combine-repos-workflow-937fs4`
- Koordiniert mit SHADED-Branch (selber Name)
- Manifest-Export ist bereits in `core/exporter.py` implementiert
- Tests in `tests/test_exporter_manifest.py` validieren Round-Trip-Kompatibilität

## Lizenz

MIT (oder wie im Projekt definiert)
