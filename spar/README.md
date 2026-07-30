# SPAR — engine-agnostischer Fighter-Core

Ein Datenformat für framegenaue Kampfanimation plus eine engine-freie
Referenz-Implementierung.

**Das Format ist das Produkt.** Implementierungen sind austauschbar. Der Beweis dafür wird
die Conformance-Suite sein: zwei unabhängige Implementierungen, dieselben Vektoren,
identische Ausgabe. Solange nur eine existiert, ist Engine-Agnostik Absicht und nicht
Nachweis — siehe *Stand* unten.

## Schichten

| | Schicht | Was | Stand |
|---|---|---|---|
| L1 | Anatomiegraph | Was ein Körper *ist*: Gelenke, Segmente, Grenzen, Kontakte | steht |
| L2 | Posegraph | Was er über die Zeit *tut*: Rotation je Gelenk je Frame | steht |
| L3 | Kontaktgraph | Woran er *koppelt*: Boden, Griff, Treffer | steht — Kontaktplan, kontakt-erhaltendes Retargeting |
| L4 | Ausdrucksgraph | Gesicht, eine Auflösungsstufe feiner | offen |
| L5 | Intent | *Warum* es passiert — zuerst als Beschriftung, nicht als Erzeuger | offen |
| L6 | CUE-Prüfung | Stimmt das? | steht |

L6 kommt bewusst vor L4 und L5. Prüfungen machen die unteren Schichten falsifizierbar:
ohne sie ist „die Bewegung sieht besser aus" Geschmack, mit ihnen ist Fußrutschen eine Zahl.

## Datenformate

```
Video/GIF ──► capture.json ──► clip.glb ──► clip.combat.json ──► clip.baked.json
              verrauscht       Standard      Autoren-Format       Runtime
```

| Schicht | Format | Warum |
|---|---|---|
| Rig | `spar-rig/1` | Anatomie als Datendatei. Kein Standard deckt Gelenkgrenzen und Kontaktrollen ab. |
| Capture | `swift-capture/1` | Verrauschte Beobachtung mit Konfidenz, Shots, Provenienz. Kein Standard. |
| Clip | glTF 2.0 `.glb` | Khronos-Standard. PlayCanvas, Three.js, Godot, Unity, Unreal, Blender laden das ohne Adapter-Code. |
| Combat | `fcd/1` | Frame-Events, Hit-/Hurtboxen, Cancel-Windows. Kennt glTF nicht. |
| Baked | `fcd-baked/1` | Weltraum-Hitboxen als Fixed-Point-Integer. Macht die Simulation deterministisch. |

Erfunden wurde nur, was es nicht gibt.

## Zwei Kernaussagen

**Knochenlängen sind unveränderlich.** Perspektivische Verkürzung entsteht ausschließlich
durch Rotation — ein Arm, der in der Projektion kürzer wird, ist rotiert, er kann nicht
kürzer *sein*. Deshalb verbietet das glTF-Profil `scale`, und deshalb prüft
`cue.check_bone_lengths` das über jeden Clip.

**Anatomie ist Daten, kein Code.** `biped/1` (17 Bones) ist das erste Exemplar, nicht das
Format; `hexapod/1` (21 Bones, sechs Beine) lädt und rendert ohne eine Zeile Codeänderung.
Anthropozentrik ist damit keine Annahme mehr.

## Determinismus

Damit PlayCanvas, Godot und ein Headless-Runner dieselbe Simulation ergeben:

- **Gameplay-Zustand ist ausschließlich Integer.** Positionen in 1/256 Weltenheiten
  (1 Weltenheit = 1 Meter, Auflösung ≈ 3,9 mm), Frame-Zähler als `int`.
- **Hitbox-Welttransforms werden zur Bake-Zeit vorberechnet.** Clips sind vorautorisiert,
  die Pose je Frame steht fest — die Runtime führt im Gameplay-Pfad **null Float-FK** aus.
  Kollision ist Integer-Lookup plus Integer-Test.
- **Float-FK nur zum Rendern.** Interpolation zwischen Frames ist rein optisch.
- **RNG:** xorshift128, in der Spec festgelegt, nie die Zufallsfunktion der Wirtssprache.
- **Replay = Input-Log + Seed**, nicht serialisierter Objektzustand.

Preis: Posen, die zur Laufzeit prozedural verändert werden (IK, Ragdoll), können keine
Gameplay-Boxen tragen. Für einen Fighter ist das kein Verlust — framegenaue
Autorenkontrolle ist dort ohnehin die Anforderung.

## Aufbau

```
spec/     Schemata und verbindliche Konventionen
rigs/     Anatomiegraphen (biped/1, hexapod/1)
ref_py/   Referenz-Implementierung: engine-frei, kein Renderer im Gameplay-Pfad
```

## Schnellstart

```bash
cd spar/ref_py
pip install -r ../requirements-dev.txt

pytest tests                                    # ohne SWIFT-Abhängigkeiten
python -m spar.cli rigs                         # mitgelieferte Anatomien
python -m spar.cli build-gold -o build          # Gold-Clip: glb + combat + bake
python -m spar.cli validate build/jab.glb       # glTF-Profil prüfen
python -m spar.cli check build/jab.glb          # CUE: Längen, Grenzen, Rutschen, Balance
python -m spar.cli render build/jab.glb --baked build/jab.baked.json -o build/frames
python -m spar.cli conformance                  # 19 Vektoren, nach Rolle gestaffelt

# L3: Kontakte als Invariante
python -m spar.cli contacts build/jab.glb -o build/jab.contacts.json
python -m spar.cli retarget build/jab.glb --to biped/1-stocky \
    --contacts build/jab.contacts.json -o build/jab_stocky.glb
python -m spar.cli --rig biped/1-stocky check build/jab_stocky.glb \
    --contacts build/jab.contacts.json
```

Der Renderer ist bewusst hässlich. Sein Zweck ist der Nachweis, dass das Format **ohne
Engine** sichtbar ist — wer Clips nur in PlayCanvas betrachten kann, hat keine
engine-agnostische Pipeline, sondern eine mit einem bequemen Betrachter.

## Stand

Fertig: L1 (Rig-Format, zwei Anatomien), L2 (glTF-Profil, Lesen/Schreiben, FK, Mirror-Bake),
L3 (Kontaktplan `spar-contact/1`, kontakt-erhaltendes Retargeting per Zwei-Knochen-IK),
L6 (Längen, Gelenkgrenzen per Swing-Twist, Kontaktdrift, Schwerpunkt über Stützfläche),
Fixed-Point-Bake, deterministische Simulation, Headless-Viewer, Gold-Clip,
19 Conformance-Vektoren über sechs Stufen mit Meta-Tests.

Retargeting deckt **gleiche Topologie, andere Proportionen** ab. Übertragung zwischen
verschiedenen Topologien braucht eine Gliedmaßen-Zuordnung und ist ein eigenes Vorhaben;
der Sechsbeiner läuft hier nur als Generalitätsnachweis durch denselben Löser.

Offen: TypeScript-Implementierung, PlayCanvas-Adapter, Durchdringungsprüfung (braucht
Volumen, nicht nur Kontaktpunkte), Extraktion aus Video, Editor, L4, L5.

**Noch nicht bewiesen:** Bis die zweite Implementierung dieselben Vektoren besteht, ist
„engine-agnostisch" eine Konstruktionsabsicht und keine geprüfte Eigenschaft. Abweichung
zwischen zwei konformen Implementierungen wäre dann eine **Spec-Lücke**, kein
Implementierungsfehler — der Vektor gehört in die Suite, bevor der Code repariert wird.
