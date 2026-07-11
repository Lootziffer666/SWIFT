# SWIFT

**Sprite-Werkzeug für Windy, Interactive, Frames, Tinting** – ein Python/Blender-CLI zur Generierung von animierten Pixel-Art-Sprite-Sheets aus FBX-Charaktermodellen.

## Übersicht

SWIFT rendert 3D-Charaktere in Blender headless zu animierten Sprite-Sheets (PNG) mit automatisch erzeugten **Manifesten** (JSON) für Frame-Layout und Animationen. Die erzeugten Sheets sind direkt kompatibel mit SHADED's Actor-System via `window.SHADED.addActor()`.

```bash
python main.py render \
  --model character.fbx \
  --anim idle \
  --format sprite_sheet \
  --output output
# Output: output.png (RGBA), output_manifest.json (v1.4.0)
```

Das erzeugte Manifest kann sofort in SHADED geladen werden – keine weitere Konfiguration nötig.

## Ecosystem & Orchestration

SWIFT ist der **Character-/Actor-Produktionsknoten** im agentischen Spiele-Studio (beschrieben in `assetpilot.md`). Es nimmt 3D-Charaktermodelle entgegen und liefert animierte Sprite-Sheets + JSON-Manifeste, die SHADED über `window.SHADED.addActor({ image, manifest, ... })` als rein optische Actors in die Welt einfügt. SWIFT verändert dabei keine Weltzustände – es ist der reine Darstellungsknoten für Figuren (siehe Invariante 2 unten).

Die sechs Rollen des Ökosystems und SWIFT's Verhältnis zu ihnen:

- **mini-me** (Ideengenerator): Liefert Charakterkonzepte; SWIFT realisiert sie als renderbare FBX→Sprite-Sheet-Actors.
- **Asset Pilot** (Produktionsleiter, SQLite, ~2470 Assets): Orchestriert SWIFT als einen der erzeugenden Generatoren für Actor-Assets.
- **SHADED** (Weltkleber / Weltzustands-Kohärenz): Konsumiert SWIFT's Sprite-Sheets + Manifeste via `addActor()` als optische Actors – ohne dass SWIFT SHADED's Material-Klassifikation beeinflusst.
- **3D-RE-GEN** (räumlicher Bild→3D-Sensor): Liefert die räumliche Basis (Tiefe, Objektgrenzen); SWIFT nutzt 3D-Modelle als Eingabe und erzeugt die animierte Figurendarstellung.
- **ANVIL** (Orchestrator der Generatoren): Treibt SWIFT als Generator-Knoten (Charakter-/Actor-Produktion) im Gesamtprozess.
- **CUE-AGENT** (Playability-Gatekeeper): Prüft die von SWIFT erzeugten Actors auf zeitliche/Spiel-Konsistenz im fertigen Raum.

Das **TRON-Prinzip** gilt auch für SWIFT: Bedeutung, Raum und Weltzustand bleiben explizit & deterministisch – die KI (Blender-Render, optionales Neural Rendering) ist nur der letzte Darstellungsschritt. Die vollständige Orchestrierungs-/CLI-Vereinbarung ist in `docs/ORCHESTRATION.md` beschrieben; eine knappe Zusammenfassung von SWIFT's Platz im Ökosystem findet sich in `docs/ECOSYSTEM.md`.

**MetaHuman als Charakterquelle:** Epics MetaHumans (UE-FBX-Export) sind direkter
SWIFT-Input für realistische menschliche Figuren – Workflow, Export-Einstellungen
und Lizenzrahmen in [`docs/METAHUMAN.md`](docs/METAHUMAN.md). Die Anim-Library
erkennt MetaHuman-Dateien (`metahuman`-Pfade, `MH_`-Präfix) als eigene Quelle.

## Installation

```bash
pip install -r requirements.txt
# Blender 3.x+ erforderlich (wird per subprocess aufgerufen)
apt-get install -y blender  # oder brew install blender (macOS)
```

## Commands

SWIFT bietet ein CLI (`python main.py <subcommand>` bzw. den `swift`-Launcher) sowie
eine PySide6-GUI. Alle Unterbefehle akzeptieren `--json` / `--json-summary` für die
maschinenlesbare ANVIL-Anbindung (Vertrag in `docs/ORCHESTRATION.md`).

### GUI (Render / Analyze / Mocap / Video2Sprite / SpriteSheet)

```bash
python -m gui.app     # startet die PySide6-GUI
swift gui             # Äquivalent über den CLI-Launcher
```

Die GUI (`gui/app.py`) kapselt die CLI-Unterbefehle in Tabs: **Render**, **Analyze**,
**Mocap**, **Video2Sprite**, **SpriteSheet**. Der Render-Tab stellt u. a. ein
**World-states**-Textfeld bereit (Platzhalter `dust,aging=0.7`), über das die
SHADED-Weltzustands-Varianten direkt konfiguriert werden – die Varianten entstehen als
deterministische Pillow/NumPy-Transformationen, also ohne Blender-Laufzeit. Ebenso gibt
es das Textfeld **Palette variants** (Platzhalter `red,green`) für Runtime-Farbvarianten
(via `--variants`, siehe Abschnitt *Palette-Swapping*).

### Maschinenlesbares CLI (`--json-summary`)

Jeder Unterbefehl gibt mit `--json` (Alias `--json-summary`) bei Erfolg **ein einziges
JSON-Objekt nach STDOUT** aus; aller Fortschritt/alle Diagnose landen auf STDERR. Bei
Fehler wird `{"status":"error","error":<msg>}` nach STDERR geschrieben und der Prozess
endet nicht-null.

```bash
python main.py render --model hero.fbx --world-states dust,aging --json
#   stdout: {"status":"success","command":"render","artifacts":[...],"manifest_path":"...","sheet_path":"...","depth_path":null,"world_states":["dust","aging"],"fps":12,"frame_count":24,"animation_names":["walk"],"mapping_version":"1.4.0"}
#   stderr: (Fortschritt/Diagnose)
```

**Exit-Codes (SWIFT ↔ ANVIL Vertrag, siehe `docs/ORCHESTRATION.md` §1):**

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg (bzw. nur Hilfe ohne Subcommand). |
| `1` | Allgemeiner Fehler (Render-/Tracking-Fehler, unbehandelte Ausnahme). |
| `2` | Fehlende Eingabe (Datei/Wert): Modell-FBX, Video, Sheet, Manifest, `--anim`/`--frame` oder API-Key fehlt. |
| `3` | Externes Werkzeug fehlt: Blender (`render`) bzw. PySide6 (`gui`). |

### End-to-End-Demo (ohne Blender)

`scripts/demo_actor_pipeline.py` führt den kompletten SHADED-ready Actor-Pfad CI-tauglich
aus – ohne Blender und ohne SHADED-Laufzeit:

```bash
python scripts/demo_actor_pipeline.py                   # 6 Frames, idle, dust/aging/heat/soot
python scripts/demo_actor_pipeline.py --depth           # zusätzlich Depth-Sheet
python scripts/demo_actor_pipeline.py --out artifacts/actor_demo
```

Es erzeugt ein addActor-kompatibles Basis-Sheet (PNG) + Manifest (JSON v1.4.0) sowie pro
Weltzustand eine Varianten-PNG (`<anim>_<state>.png`) und validiert abschließend
addActor-Kompatibilität + Manifest-Round-Trip. Details in `docs/ECOSYSTEM.md`.

### Unterbefehle (Kurzreferenz)

| Subcommand | Zweck | Wichtigste Flags |
|------------|-------|------------------|
| `render` | FBX → Sprite-Sheet (+ Manifest, optional Depth/Varianten/Weltzustände) | `--model` (req), `--anim`, `--output`, `--format`, `--world-states`, `--variants`, `--depth-pass`, `--skeleton-generator`, `--height-cm`, `--weight-kg`, `--with-ik`, `--mesh-bodies`, `--skeleton-output` |
| `analyze` | Referenz-Sheet → StyleParams (Claude Vision) | `sheet` (pos), `--api-key` |
| `mocap` | Video → BVH | `video` (pos), `--output` |
| `video2sprite` | Video → Pixel-Art-Sheet | `video` (pos), `--format`, `--width`/`--height`, `--colors`, `--keyframes` |
| `spritesheet` | Sheet + Manifest inspizieren/re-exportieren | `action` (list/export/extract), `image` (pos), `--manifest`, `--anim`, `--frame` |
| `anims` | FBX/BVH-Animationsbibliothek scannen & listen (Quelle, Root-Motion) | `paths` (pos), `--query`, `--source`, `--no-recursive` |
| `gui` | PySide6-GUI starten | – |

Beispiel (Render mit Weltzuständen + Manifest):

```bash
python main.py render \
  --model character.fbx \
  --anim walk \
  --output out/hero \
  --world-states "dust,aging" \
  --format sprite_sheet
# Erzeugt: out/hero.png, out/hero_manifest.json, out/hero_dust.png, out/hero_aging.png
```

Die vollständige CLI-/Orchestrierungsvereinbarung (alle Flags, Artefakte, Manifest-Schema
inkl. `worldStates`) ist in `docs/ORCHESTRATION.md` dokumentiert; SWIFT's Rolle im
Ökosystem in `docs/ECOSYSTEM.md`.

## Manifest-Schema (v1.4.0)

```json
{
  "mappingVersion": "1.4.0",
  "sourceImage": { "w": 512, "h": 256 },
  "frameRects": {
    "F01": {"x": 0, "y": 0, "w": 128, "h": 256},
    "F02": {"x": 128, "y": 0, "w": 128, "h": 256}
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
- `frameRects`: Koordinaten jedes Frames im Sheet als Objekt `{"x","y","w","h"}` (nicht als Array)
- `frames`: Frame-Metadaten mit eindeutigem ID + semantischem Key
- `animations`: Benannte Animations-Sequenzen mit FPS und Loop-Flag

**Phase B2 – Optional Depth-Map Support:**
```json
{
  ...
  "depthImage": "output_depth.png",
  "depthSourceImage": { "w": 512, "h": 256 },
  "depthFrameRects": {
    "F01": {"x": 0, "y": 0, "w": 128, "h": 256},
    "F02": {"x": 128, "y": 0, "w": 128, "h": 256}
  }
}
```

> **Schema ist autoritativ in `docs/ORCHESTRATION.md` (§4):** dort sind die optionalen
> Felder `appliesTo`, `variants` und `worldStates` (SHADED-Weltzustands-Hooks aus
> `--world-states`) sowie die exakte Rect-Kodierung (`{"x","y","w","h"}`, nicht Array)
> vollständig dokumentiert. Die Tabelle oben ist eine Kurzfassung.

## SWIFT → SHADED Integration

Das erzeugte Manifest + Sprite-Sheet können direkt in SHADED geladen werden:

```html
<!-- index.html / Browser-Test -->
<script>
// addActor nimmt das Manifest als OBJEKT (oder JSON-Text) entgegen – nicht als
// Datei-URL. Und: das Manifest-Feld "depthImage" wird von addActor NICHT
// automatisch geladen; die Depth-Map wird als eigene Option übergeben.
const manifest = await fetch('output_manifest.json').then(r => r.json());
const actor = SHADED.addActor({
  image: 'output.png',           // Sprite-Sheet (URL oder HTMLImageElement)
  manifest,                      // Manifest-Objekt (v1.4.0)
  depthImage: manifest.depthImage || undefined, // optional: Depth-Sheet explizit
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

## Phase 2+ Features (implementiert)

### Depth-Rendering (Tiefen-Pass)

Über `--depth-pass` wird zusätzlich zum Farb-Sheet ein Z-Buffer-Pass als
8-bit-Grayscale-PNG gerendert. Das Manifest erhält dann `depthImage`
(Basename des Depth-Sheets), `depthSourceImage` (Dimensionen) und
`depthFrameRects` (Frame-Layout, identisch zum Farb-Sheet) — SHADED nutzt diese
für räumliches Layering (`depthLayer` in `addActor`).

```bash
python main.py render \
  --model character.fbx \
  --anim walk \
  --depth-pass \
  --output out/hero
# Erzeugt: out/hero.png, out/hero_manifest.json, out/hero_depth.png
# Manifest: "depthImage": "hero_depth.png", "depthFrameRects": {...}
```

### Multi-Pass Rendering (Normal- & Emissive-Pass)

Mit `--normal-pass` bzw. `--emissive-pass` werden zusätzliche Render-Passes
erzeugt — eine Normale-Map (RGB-PNG) und ein reines Emissions-Pass
(Emissions-only RGB-PNG). Das Manifest ergänzt pro Pass
`normalImage`/`normalSourceImage`/`normalFrameRects` bzw.
`emissiveImage`/`emissiveSourceImage`/`emissiveFrameRects` (alle optional, nur
bei aktiviertem Pass vorhanden):

```bash
python main.py render \
  --model character.fbx \
  --anim walk \
  --normal-pass --emissive-pass \
  --output out/hero
# Erzeugt: out/hero_normal.png, out/hero_emissive.png
# Manifest: "normalImage": "hero_normal.png", "emissiveImage": "hero_emissive.png", ...
```

### Procedurale Skelette (Parametrische Charakter-Generierung)

Über `--skeleton-generator` wird ein parametrisches Humanoid-Skelett
(Armature + Knochen) erzeugt. Das ursprüngliche Eingabe-Modell (`--model`)
wird **nie überschrieben**.

**Ehrlicher Status:** Der FBX-Export des Rigs benötigt `bpy` und funktioniert
daher nur, wenn der Code INNERHALB von Blenders Python läuft — im normalen
CLI-Prozess wird kein FBX erzeugt (nur die verifizierbare
`<rig>_skeleton.json`-Metadatei). Damit der Befehl trotzdem end-to-end nutzbar
ist, rendert SWIFT ohne Blender einen **SDF-Preview** (`core/sdf_preview.py`):
Der prozedurale Charakter (Skelett + Kapsel-/Kugel-Formen aus
`core/procedural/character_def.py`) wird über den reinen Python-Raymarcher
(`core/sdf/`) zu transparenten RGBA-Idle-Frames gerendert und wie gewohnt zu
Sheet + kanonischem v1.4.0-Manifest exportiert — direkt
`SHADED.addActor()`-kompatibel. Qualität: stilisiertes Mannequin (Preview),
kein Ersatz für echte FBX-Renders.

- Ohne `--skeleton-output` wird das Rig neben dem Eingabemodell abgelegt:
  `<model>_procedural.fbx` (nur mit bpy).
- Mit `--skeleton-output <pfad>` wird ein beliebiger Zielpfad erzwungen.

Parameter steuern Proportionen und Ausstattung:

| Flag | Bedeutung | Default |
|------|-----------|---------|
| `--height-cm` | Körpergröße in cm (skaliert alle Knochenlängen linear) | `170.0` |
| `--weight-kg` | Gewicht in kg (skaliert Knochen-Dicke der Mesh-Bodies ∝ ³√Gewicht) | `70.0` |
| `--with-ik` | 2-Knochen-IK-Ketten an Armen/Beinen (Hand.L/R, Foot.L/R) | aus |
| `--mesh-bodies` | Kapsel-Mesh-Körper pro Knochen (Radius ∝ Gewicht, Länge ∝ Knochen) | aus |
| `--skeleton-output` | Ziel-FBX für das generierte Rig (Original bleibt erhalten) | `<model>_procedural.fbx` |

Beispiel:

```bash
python main.py render \
  --model character.fbx \
  --skeleton-generator \
  --height-cm 185 --weight-kg 90 \
  --with-ik --mesh-bodies \
  --output out/hero
# Mit Blender+bpy: rendert character_procedural.fbx (Original unverändert).
# Ohne Blender:    SDF-Preview -> out/hero.png + out/hero_manifest.json
#                  (+ out/hero_depth.png bei --depth-pass)
```

Die IK-Ketten- und Mesh-Body-Geometrie werden rein (ohne Blender) berechnet und
sind per Unit-Test verifizierbar (`tests/test_skeleton_procedural_math.py`);
der SDF-Preview-Pfad in `tests/test_sdf_preview.py`.

### Palette-Swapping (Runtime-Farbvarianten)

Farbsvarianten eines bereits gerenderten Sheets entstehen **rein zur Laufzeit**
(Pillow-LUT-Pass), also **ohne Blender und ohne Neurender**. Das ist ideal für
schnelle Personalisierung (z. B. Team-Farben, Skins).

Zwei Syntaxen für `--variants` (Komma-getrennt):

- **Benannte Presets** — `red,green,purple,gold` (vordefinierte Rampe auf das
  kanonische „Team-Blau" des Renderers):
  ```bash
  python main.py render --model hero.fbx --output out/hero --variants "red,green"
  # Erzeugt: out/hero_red.png, out/hero_green.png  +  manifest['variants']
  ```
- **Eigene Hex-Maps** — `name=#Src:Dst` definiert beliebige Quell→Ziel-Tausche
  zur Laufzeit (kein Re-Render nötig). Mehrere Paare mit `;` trennen:
  ```bash
  python main.py render --model hero.fbx --output out/hero \
    --variants "team_red=#4169E1:#FF6347"
  # Erzeugt: out/hero_team_red.png  (Quell-Farbe #4169E1 -> #FF6347)
  python main.py render --model hero.fbx --output out/hero \
    --variants "x=#AABBCC:#112233;#DDEEFF:#445566"
  ```

Pro Variante wird `<base>_<name>.png` geschrieben und das Manifest um
`"variants": [{"name": ..., "path": ...}, ...]` ergänzt. Die PNGs sind
deterministisch (timestamp-frei), und die `variants`-Liste round-trip-t über
`SpriteSheetManifest`. Der GUI-Render-Tab stellt dafür das Textfeld
**Palette variants** (Platzhalter `red,green`) bereit.


## Bekannte Einschränkungen

- **BVH-Export (`mocap`) ist partiell:** `core/mocap/bvh_exporter.py` schreibt
  für Nicht-Root-Gelenke Null-Rotationen (Positions-Tracking ohne IK-Solver).
  Die BVH-Dateien sind als Trajektorien-Rohdaten nutzbar, nicht als fertige
  Retarget-Animationen.
- **`core/video_to_sprite/ai_stylizer.py` ist experimentell und NICHT in die
  Pipeline verdrahtet:** Es referenziert externe/private Bildmodelle und wird
  von `video2sprite` bewusst nicht aufgerufen.
- **Web-Demo:** benötigt zusätzlich `pip install -r web/requirements-web.txt`
  (FastAPI/uvicorn sind absichtlich nicht in der Haupt-`requirements.txt`).
- **`--skeleton-generator` ohne Blender** liefert den stilisierten SDF-Preview
  (siehe oben), keine FBX-Qualität.

## Abhängigkeiten

| Paket | Zweck |
|-------|-------|
| `Pillow` | PNG-Verarbeitung (Sprite-Sheet Packing) |
| `Blender 3.x+` | Headless-Rendering via subprocess |
| `pytest` | Unit-Tests |

Blender wird NICHT als Python-Modul importiert, sondern via Subprocess aufgerufen (`blender --background --python ...`). Das erlaubt flexible Blender-Versionen und sichere Parallelisierung.

## Zukunfts-Erweiterungen

Die ursprünglich hier gelisteten Phase-2+-Features — Depth-Rendering,
Procedurale Skelette, Palette-Swapping und Multi-Pass Rendering
(Normal/Emissive) — sind **bereits implementiert** und unter
[*Phase 2+ Features (implementiert)*](#phase-2-features-implementiert)
dokumentiert. Hier folgen nur noch offene, nicht umgesetzte Ideen:

- *Platzhalter für künftige Erweiterungen (z. B. weiteres Multi-Channel-Rendering,
  komplexere IK-Topologien).*

## Git & Branches

- Branch: `claude/combine-repos-workflow-937fs4`
- Koordiniert mit SHADED-Branch (selber Name)
- Manifest-Export ist bereits in `core/exporter.py` implementiert
- Tests in `tests/test_exporter_manifest.py` validieren Round-Trip-Kompatibilität

## Lizenz

MIT (oder wie im Projekt definiert)
