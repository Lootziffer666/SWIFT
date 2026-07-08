# SWIFT im ANVIL/SHADED-Ökosystem

SWIFT (Sprite-Werkzeug für Windy, Interactive, Frames, Tinting) ist der
**Character-/Actor-Produktionsknoten** des agentischen Spiele-Studios, das in
`assetpilot.md` beschrieben ist.

## Rolle in der Pipeline

```
FBX-Charaktermodell
    ↓  SWIFT (render)
animiertes Sprite-Sheet (PNG) + Manifest (JSON v1.4.0)
    ↓  SHADED.addActor({ image, manifest, ... })
optischer Actor in der kohärenten Welt
```

SWIFT verändert keine Weltzustände (Staub, Hitze, Ruß, Alterung, …) – es liefert
ausschließlich die Darstellung der Figur. Das ist **Invariante 2 (Material
Truth)**: Actors sind rein optisch und greifen nicht in SHADED's
Material-Klassifikation oder Physik ein.

## Verhältnis zu den sechs Rollen

- **mini-me** – Ideengenerator; SWIFT realisiert Charakterideen als FBX→Sheet-Actors.
- **Asset Pilot** – Produktionsleiter; orchestriert SWIFT als erzeugenden Generator.
- **SHADED** – Weltkleber; konsumiert SWIFT's Sheets + Manifeste via `addActor()`.
- **3D-RE-GEN** – räumlicher Sensor; liefert die räumliche Basis, SWIFT die Animationsdarstellung.
- **ANVIL** – Orchestrator; treibt SWIFT als Generator-Knoten im Gesamtprozess.
- **CUE-AGENT** – Playability-Gatekeeper; prüft SWIFT's Actors auf Konsistenz.

## TRON-Prinzip

Bedeutung, Raum und Weltzustand bleiben explizit & deterministisch. Die KI
(Blender-Headless-Render, optionales Neural Rendering) ist nur der finale
Darstellungsschritt.

Siehe `README.md` (Abschnitt *Ecosystem & Orchestration*) für die technische
Pipeline sowie `docs/ORCHESTRATION.md` für die ANVIL-/SHADED-Integrationsvereinbarung.

## End-to-End-Demo: SHADED-ready Actor-Harness

`scripts/demo_actor_pipeline.py` führt den **kompletten** SWIFT-Actor-Pfad
end-to-end aus – ohne Blender und ohne die externe SHADED-Laufzeit, also
CI-tauglich:

```
FBX → (Blender-Render) → Basis-Sprite-Sheet
   ↓  core.exporter.Exporter (Verpackung zu PNG)
Weltzustands-Varianten (core.procedural.world_states: dust, aging, heat, soot, …)
   ↓  Transform auf das Sheet → <anim>_<state>.png
SpriteSheetManifest (frameRects, frames, animations, worldStates, optional depth)
   ↓  core.exporter.Exporter (Manifest v1.4.0 + PNG)
SHADED.addActor({ image, manifest, x, y, scale, anim, depthLayer })
```

### Ausführen

```bash
python scripts/demo_actor_pipeline.py                 # Standard: 6 Frames, idle, dust/aging/heat/soot
python scripts/demo_actor_pipeline.py --depth         # zusätzlich optionales Depth-Sheet
python scripts/demo_actor_pipeline.py --frames 8 --fps 24 --states dust,soot
python scripts/demo_actor_pipeline.py --out artifacts/actor_demo
```

### Erzeugte Artefakte (in `--out`, Default `artifacts/actor_demo`)

- `<anim>_sheet.png` – verpacktes Basis-Sprite-Sheet (RGBA).
- `<anim>_manifest.json` – `SpriteSheetManifest` v1.4.0 (addActor-kompatibel).
- `<anim>_<state>.png` – eine Weltzustands-Variante pro Transform.
- `<anim>_depth.png` (+ `depthFrameRects`) – nur mit `--depth`.
- `<anim>_manifest.roundtrip.json` – Hilfsdatei des Round-Trip-Validierungstests.

Das Skript validiert abschließend:
1. **addActor-Kompatibilität** – Pflichtschlüssel (`mappingVersion`,
   `sourceImage`, `frameRects`, `frames`, `animations`) vorhanden; ein
   `MockSHADED`-Stub zeichnet den `addActor(...)`-Aufruf auf.
2. **Manifest-Round-Trip** – write → read → write, Strukturgleichheit.

### Blender vs. CI

- Der **FBX → Render**-Schritt benötigt lokal installiertes **Blender**
  (`scripts/blender_render.py`). Er ist im Harness derzeit nicht verdrahtet;
  stattdessen wird ein **synthetischer Pillow-Character** (einfache animierte
  Form) als Basis-Sheet erzeugt.
- Die Schritte **Verpacken, Weltzustands-Varianten und Manifest-Export**
  laufen **überall** (reine Python/Pillow/NumPy, keine externen Tools) und
  werden so in CI geprüft (`tests/test_e2e_actor_pipeline.py`).

Siehe auch `tests/test_e2e_actor_pipeline.py` für die automatisierte
addActor-/Round-Trip-Validierung.
