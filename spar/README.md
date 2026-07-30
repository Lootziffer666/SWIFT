# SPAR — engine-agnostischer Fighter-Core

Ein Datenformat für framegenaue Kampfanimationen plus eine engine-freie Referenz-Implementierung.

**Das Format ist das Produkt.** Implementierungen sind austauschbar. Der Beweis dafür ist
die Conformance-Suite: zwei unabhängige Implementierungen, dieselben Vektoren, identische
Ausgabe.

## Drei Datenschichten

```
Video/GIF ──► capture.json ──► clip.glb ──► clip.combat.json ──► clip.baked.json
              verrauscht       Standard      Autoren-Format       Runtime
              (eigene Spec)    (glTF 2.0)    (eigene Spec)        (Fixed-Point)
```

| Schicht | Format | Warum |
|---|---|---|
| Capture | `swift-capture/1` | Verrauschte Beobachtung mit Konfidenz, Shots, Provenienz. Kein Standard deckt das ab. |
| Clip | glTF 2.0 `.glb` | Khronos-Standard. PlayCanvas, Three.js, Godot, Unity, Unreal, Blender laden das ohne Adapter-Code. |
| Combat | `fcd/1` | Frame-Events, Hit-/Hurtboxen, Cancel-Windows. Kennt glTF nicht. |
| Baked | `fcd-baked/1` | Weltraum-Hitboxen als Fixed-Point-Integer. Macht die Simulation deterministisch. |

Nur erfunden wurde, was es nicht gibt.

## Determinismus

Damit PlayCanvas, Godot und ein Headless-Runner dieselbe Simulation ergeben:

- **Gameplay-Zustand ist ausschließlich Integer.** Positionen in 1/256 Weltenheiten
  (`UNIT_SCALE = 256`, 1 Weltenheit = 1 Meter, Auflösung ≈ 3,9 mm), Frame-Zähler als `int`.
- **Hitbox-Welttransforms werden zur Bake-Zeit vorberechnet.** Clips sind vorautorisiert,
  die Pose pro Frame steht fest — die Runtime führt im Gameplay-Pfad **null Float-FK** aus.
  Kollision ist Integer-Lookup plus Integer-Test. 3D-Genauigkeit optisch,
  Integer-Determinismus im Kampf.
- **Float-FK nur zum Rendern.** Interpolation zwischen Frames ist rein optisch und darf
  keine Kampfentscheidung beeinflussen.
- **RNG:** xorshift128, in der Spec festgelegt. Niemals die Zufallsfunktion der Wirtssprache.
- **Replay = Input-Log + Seed**, nicht serialisierter Objektzustand.

## Aufbau

```
spec/         Schemata und verbindliche Konventionen
ref_py/       Referenz-Implementierung (Python, engine-frei, kein Renderer)
conformance/  Golden Vectors — JSON rein, JSON raus, sprachneutral
```

## Schnellstart

```bash
cd spar
pip install -r requirements.txt

# Gold-Clip bauen (glTF + Combat-Sidecar + Bake)
python -m spar.cli build-gold --out build/

# Headless rendern — beweist, dass das Format ohne Engine sichtbar ist
python -m spar.cli render build/jab.glb --combat build/jab.combat.json --out build/frames/

# Conformance-Suite
python -m spar.cli conformance conformance/vectors/
```

## Konformität

Eine Implementierung gilt als konform, wenn sie alle Vektoren in `conformance/vectors/`
besteht. Siehe `conformance/RUNNER.md`.

Abweichung zwischen zwei konformen Implementierungen ist eine **Spec-Lücke**, kein
Implementierungsfehler — der Vektor gehört dann in die Suite, bevor der Code repariert wird.
