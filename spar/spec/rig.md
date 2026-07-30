# Rig-Format `spar-rig/1`

L1, der Anatomiegraph: **was ein Körper ist.**

Ein Rig ist eine Datendatei, kein Sonderfall im Code. `biped/1` ist das erste Exemplar,
nicht das Format. Sechsarmiger Dämon, Spinne, Zentaur, Drache, segmentierte Wirbelsäule und
Schwanz sind weitere Dateien — kein Sonderweg. Anthropozentrik verschwindet dadurch nicht
als Feature, sondern als Annahme.

Mitgeliefert in `spar/rigs/`:

| Rig | Bones | Endeffektoren | Wurzel |
|---|---|---|---|
| `biped/1` | 17 | 4 | `Hips` |
| `hexapod/1` | 21 | 6 | `Thorax` |

## Aufbau

```json
{
  "schema": "spar-rig/1",
  "id": "biped/1",
  "units": "meters",
  "up": "Y",
  "forward": "-Z",
  "root": "Hips",
  "bones": [ ... ],
  "symmetry": { "Arm.L": "Arm.R" },
  "contacts": [ ... ],
  "mass_distribution": { "Chest": 0.18 }
}
```

### Bones

```json
{
  "name": "Forearm.R",
  "parent": "Arm.R",
  "offset": [0.15, 0.0, 0.0],
  "joint": { "type": "hinge", "axis": [0,0,1], "range": [-150.0, 0.0] },
  "load_bearing": false,
  "roles": ["end_effector", "grip"]
}
```

`offset` ist die Rest-Translation relativ zum Elternteil, in Metern. Die Reihenfolge in der
Datei ist **frei** — der Loader sortiert topologisch, sodass Eltern immer vor Kindern
stehen, und meldet Zyklen sowie von der Wurzel unerreichbare Bones.

**Knochenlängen sind unveränderlich.** Sie werden weder animiert noch skaliert. Das ist
keine Bequemlichkeit, sondern die Kernaussage des Formats: perspektivische Verkürzung
entsteht ausschließlich durch Rotation. Ein Arm, der in der Projektion kürzer wird, ist
rotiert — er kann nicht kürzer *sein*. Genau deshalb verbietet das glTF-Profil `scale`, und
genau deshalb prüft `cue.check_bone_lengths` das über jeden Clip.

Charaktere anderer Proportion entstehen durch einen anderen Satz `offset`-Werte bei
identischen Rotationskanälen (Retargeting). Skalierung ist gleichförmig pro Rig, nie pro
Frame.

### Gelenke

| Typ | DOF | Felder | Wofür |
|---|---|---|---|
| `fixed` | 0 | — | starre Verbindungen |
| `hinge` | 1 | `axis`, `range` (Grad) | Ellbogen, Knie — sie biegen nur in **eine** Richtung |
| `ball` | 3 | `swing` (halber Öffnungswinkel), `twist` (Grad-Bereich) | Schultern, Hüften, Wirbelsäule |

Geprüft wird per Swing-Twist-Zerlegung (`cue.swing_twist`): Der Anteil des
Quaternion-Vektors entlang der Achse ergibt die Drehung, der Rest den Schwenk. Bei einem
Scharnier ist jeder Schwenk ungleich null bereits eine Verletzung — das Gelenk hat diese
Freiheit nicht.

Dieselben Grenzen tragen den Holzpuppen-Editor: Gliedmaßen lassen sich nur so verschieben,
wie das Gelenk es zulässt.

### Symmetrie

Nur ein Paar je Beziehung nennen; der Loader ergänzt die Gegenrichtung. Nichtgenanntes
spiegelt auf sich selbst.

Gespiegelt wird an der YZ-Ebene als **eigener Bake-Schritt** (`mirror.py`), nie implizit im
Renderer oder FK:

1. Rotationskanäle über die Symmetrietabelle **tauschen**
2. Quaternion je Bone spiegeln: `(x, y, z, w) → (x, −y, −z, w)`
3. Root-Translation: `x → −x`
4. Box-Offsets: `min.x' = −max.x`, `max.x' = −min.x`

Punkt 4 ist der, an dem naive Implementierungen scheitern. `x → −x` einzeln auf `min` und
`max` angewandt vertauscht die beiden und verschiebt die Box um ihre eigene Breite.

Ein zweiter Fallstrick, den ein `facingSign`-Faktor im FK nicht abfängt: Arme liegen in Ruhe
entlang `+X` und `−X`. Eine Drehung um Z bildet `(1,0)` auf `(cos, sin)` ab, aber `(−1,0)`
auf `(−cos, −sin)` — dieselbe Bewegung nach unten braucht links das **entgegengesetzte**
Vorzeichen.

### Kontakte

```json
{ "name": "toe_l", "node": "Foot.L", "point": [0.0, -0.02, -0.11], "kind": "ground" }
```

Punkte, an denen der Körper an Welt oder Objekt koppelt. `kind` ist frei; `ground` und
`grip` werden von den CUE-Prüfungen ausgewertet.

Ein Fuß braucht **mindestens zwei** Bodenkontakte (Ferse und Zehe). Mit einem einzigen Punkt
je Fuß ist das Stützpolygon in Blickrichtung entartet, und die Balance-Prüfung meldet jeden
aufrechten Stand als Verletzung — ein Fuß ist kein Punkt.

### Massenverteilung

Anteile je Bone, Summe frei (wird normiert). Grundlage von `fk.center_of_mass` und damit der
Balance-Prüfung. Fehlt der Block, fällt der Schwerpunkt auf das ungewichtete Mittel zurück.

## Prüfen

```bash
python -m spar.cli rigs                    # mitgelieferte Rigs auflisten
python -m spar.cli --rig hexapod/1 rigs    # gegen ein anderes Rig arbeiten
```

Der Loader wirft bei fehlender Wurzel, mehreren wurzellosen Bones, unbekannten Eltern,
Zyklen, unerreichbaren Bones, Kontakten an unbekannten Nodes und Massenangaben zu
unbekannten Bones.
