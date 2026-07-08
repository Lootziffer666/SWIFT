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
