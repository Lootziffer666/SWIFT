# Conformance-Vertrag

Was eine Implementierung erfüllen muss, um als konform zu gelten.

## Warum es das gibt

Eine einzelne Implementierung beweist nichts. Ihre stillschweigenden Annahmen sind vom
Format nicht unterscheidbar — was in der Spec steht und was zufällig so codiert wurde,
sieht von innen gleich aus. Erst wenn eine zweite, unabhängig geschriebene
Implementierung dieselben Vektoren besteht, ist gezeigt, dass das Verhalten im Format
liegt.

Deshalb gilt: **Weicht eine konforme Implementierung von einer anderen ab, ist das eine
Spec-Lücke, kein Implementierungsfehler.** Der Fall gehört als Vektor in die Suite,
*bevor* Code repariert wird. Sonst wandert das Verhalten wieder still in eine
Implementierung.

## Aufbau eines Vektors

Eine Datei je Fall, `<tier>__<name>.json`:

```json
{
  "id": "sim/jab-lands",
  "tier": "sim",
  "comparison": "exact",
  "tolerance": 1e-6,
  "note": "wofür der Fall da ist",
  "input":    { ... },
  "expected": { ... }
}
```

JSON rein, JSON raus. Kein Vektor setzt eine bestimmte Sprache, ein Dateiformat oder
eine Bibliothek voraus — insbesondere braucht **kein** Vektor einen glTF-Parser. Clips
liegen als reine Rotationslisten vor.

## Stufen

Nicht jede Implementierung braucht alles. Ein dünner Engine-Adapter, der nur gebakene
Daten abspielt, muss weder glTF lesen noch Forward Kinematics rechnen.

| Stufe | Vergleich | Inhalt | Pflicht für |
|---|---|---|---|
| `fixed` | exakt | Rundungsverhalten | jede Rolle |
| `sim` | exakt | Simulation, Kollision, Treffer, Pushbox | jede spielende Rolle |
| `fk` | toleriert | Forward Kinematics, Knochenlängen | Renderer, Bake-Werkzeuge |
| `mirror` | toleriert | Spiegelung von Clips und Boxen | Bake-Werkzeuge |
| `bake` | exakt | Box-Bake in Fixed-Point | Bake-Werkzeuge |

**Rollen:**

- *Runtime* (Engine-Adapter, spielt gebakene Clips ab) → `fixed`, `sim`
- *Werkzeug* (autoriert, baked, spiegelt) → alle Stufen
- *Betrachter* (rendert nur) → `fixed`, `fk`

## Exakt oder toleriert

`"comparison": "exact"` heißt bit-genaue Gleichheit der JSON-Ausgabe. `"approx"` heißt
elementweiser Vergleich mit `tolerance`.

Diese Trennung ist keine Bequemlichkeit, sondern die Begründung für den gesamten Aufbau:
Gleitkomma ist sprachübergreifend nicht exakt reproduzierbar — `sin`, `cos` und
Quaternion-Normalisierung unterscheiden sich zwischen Plattformen und Compilern. **Deshalb
liegt der komplette Gameplay-Pfad in den Integer-Stufen.** Alles, was eine
Kampfentscheidung beeinflusst, wird exakt verglichen; toleriert wird nur, was rein
optisch ist.

## Festgeschriebene Konventionen

Diese Punkte sind Vektor-gepinnt, weil sie erfahrungsgemäß auseinanderlaufen:

**Rundung.** Halbe Werte von Null weg, nicht zur nächsten geraden Zahl. Pythons `round()`
und `numpy.round()` machen Bankers Rounding und sind hier falsch.
→ `fixed/half-away-from-zero`

**Boxen runden nach außen.** `min` abwärts, `max` aufwärts. Eine gebakene Box ist nie
kleiner als die exakte, damit Rundung keinen Treffer verschluckt.
→ `fixed/box-rounds-outward`

**Überlappung ist strikt.** Berührende Kanten zählen **nicht** als Treffer; die
Intervalle sind halboffen, der Test benutzt `<`, nicht `<=`. Ohne festgeschriebene
Konvention wählt eine Implementierung das eine und die nächste das andere, beide halten
sich für richtig — bis ein Treffer in der einen landet und in der anderen nicht.
→ `sim/boundary-touching`, `sim/boundary-one-subunit-overlap`

**Spiegelung tauscht min und max.** Bei `facing = -1` gilt `min.x' = -max.x` und
`max.x' = -min.x`. Wer `x → -x` einzeln auf beide Grenzen anwendet, vertauscht sie und
verschiebt die Box um ihre eigene Breite.
→ `sim/jab-lands`, `mirror/boxes`

**Knochenlängen sind invariant.** Die gemessene Segmentlänge muss in jedem Frame der
Rest-Länge entsprechen. Das ist die Kernaussage des Formats: Verkürzung kann nur
Rotation sein.
→ `fk/bone-lengths-are-invariant`

**Eltern vor Kindern.** Die Rig-Reihenfolge ist topologisch, ein einziger
Vorwärtsdurchlauf genügt für FK. Die Rig-*Datei* darf ihre Bones beliebig anordnen — der
Loader sortiert.
→ `fk/biped-1`, `fk/hexapod-1`

## Ausführen

Referenz-Implementierung gegen sich selbst (Regressionsschutz):

```bash
cd spar/ref_py
python -m spar.cli conformance
python -m spar.cli conformance --generate   # nach beabsichtigten Verhaltensänderungen
```

Für eine neue Implementierung: Vektoren lesen, je Stufe die entsprechende Funktion
aufrufen, Ausgabe gegen `expected` vergleichen. Mehr braucht es nicht — es gibt kein
Test-Framework zu übernehmen.

## Wenn ein Vektor sich ändert

Ein neu erzeugter Vektor, der sich vom eingecheckten unterscheidet, ist eine
Verhaltensänderung. Zwei Fälle:

1. **Beabsichtigt** — neuer Vektor wird committet, und die Änderung gehört in die
   Commit-Nachricht. Jede andere Implementierung muss nachziehen.
2. **Unbeabsichtigt** — Regression. Der Vektor hat seine Aufgabe erfüllt.

Ein Vektor darf nie stillschweigend neu erzeugt werden, um einen roten Lauf grün zu
machen. Das ist der einzige Weg, auf dem diese Suite ihren Wert verlieren kann.

## Was die Suite nicht leistet

Der Selbsttest der Referenz-Implementierung — Erzeuger und Prüfer sind derselbe Code —
ist beinahe tautologisch. Er fängt Regressionen, aber er beweist keine Korrektheit.

Geprüft wurde immerhin, dass er *überhaupt anschlägt*: Werden Overlap-Test,
Facing-Spiegelung, Rotationsverkettung, Rundungsmodus oder Box-Rundungsrichtung
verbogen, schlägt jeweils mindestens ein Vektor an. Eine Suite, die eine Verbiegung nicht
bemerkt, ist Dekoration.

Der eigentliche Beweis steht noch aus und kommt mit der zweiten Implementierung.
