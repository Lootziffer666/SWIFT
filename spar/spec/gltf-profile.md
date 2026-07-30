# glTF-Profil `spar/1`

Welche Teilmenge von glTF 2.0 ein SPAR-Clip benutzen darf. Enger als der Standard, damit
jede Engine ohne Sonderfälle dasselbe liest.

## Warum glTF und kein Eigenbau

Für 3D-Skelett und Animationskanäle existiert ein Khronos-Standard, den PlayCanvas,
Three.js, Godot, Unity, Unreal und Blender nativ laden. Ein eigenes Rig-Format würde jeden
Engine-Adapter zwingen, Skelett-Deserialisierung und Skinning selbst zu schreiben — genau
den teuren Teil, den der eingebaute Loader verschenkt.

Erfunden wird nur, was glTF nicht kennt: Kampfdaten (`fcd/1`) und verrauschte
Capture-Zwischendaten (`swift-capture/1`).

## Verbindlich

**Container.** `.glb` (Binary glTF), Version 2.0. Genau ein JSON-Chunk, genau ein BIN-Chunk.

**Achsen und Einheiten.** Y-up, rechtshändig, 1 Einheit = 1 Meter. Blickrichtung nach vorn
ist −Z. Ein Kämpfer mit `facing = +1` blickt nach +X.

**Node-Namen.** Exakt die 17 Namen aus `rig.md`, Groß-/Kleinschreibung signifikant. Ein
Clip mit abweichenden Namen ist kein SPAR-Clip. Zusätzliche Nodes (Waffen, Attachments,
Kamera) sind erlaubt, solange die 17 vollständig vorhanden sind.

**Node-Transform.** Ausschließlich `translation` und `rotation` (TRS-Form). **Kein `scale`,
keine `matrix`.** Skalierung würde Knochenlängen animierbar machen und damit die
Kernaussage des Formats brechen: dass ein Arm nur rotiert erscheinen, nicht kürzer sein
kann.

**Rest-Translation.** Die `translation` jedes Nodes entspricht dem Rest-Offset aus
`rig.md` und wird **nicht animiert** — mit einer Ausnahme: `Hips` darf einen
Translationskanal tragen (visuelle Root-Motion).

**Animationskanäle.** Nur `rotation` (Quaternion) je Node, plus optional `translation` auf
`Hips`. Kein `scale`, keine Morph-Weights.

**Interpolation.** `STEP` für alles Gameplay-Relevante. Fighter sind framegenau; eine
Zwischeninterpolation würde bedeuten, dass die gebakene Box zu Frame *n* nicht der
gezeigten Pose entspricht. `LINEAR` ist nur für rein visuelle Clips zulässig.

**Sampler-Zeiten.** Exakt `frame / fps`, aufsteigend, lückenlos ab 0. Die Sampler-Zeiten
eines Clips sind für alle Kanäle identisch.

**Quaternionen.** `(x, y, z, w)`, normalisiert, `float32`. `w ≥ 0` (kanonisches
Vorzeichen — sonst beschreiben zwei verschiedene Bit-Muster dieselbe Rotation und
Byte-Vergleiche in der Conformance-Suite schlagen grundlos fehl).

## Optional

Mesh, Skin, Material und Texturen dürfen enthalten sein und werden von der Simulation
ignoriert. Ein Clip ohne Mesh ist gültig — der Headless-Viewer zeichnet dann nur Knochen.

## Nicht erlaubt

- `scale` in Nodes oder Animationskanälen
- `matrix` statt TRS
- Animierte Rest-Translation (außer `Hips`)
- `CUBICSPLINE`-Interpolation
- Mehrere Szenen; genau eine `scene`
- Externe Buffer-URIs; alles liegt im BIN-Chunk

## Validierung

```bash
python -m spar.cli validate clip.glb
```

Prüft Profil-Konformität und meldet jede Abweichung mit Node- und Kanalnamen.
