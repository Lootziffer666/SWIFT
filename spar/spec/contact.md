# Kontaktplan — `spar-contact/1`

Schicht L3. Format: `contact.schema.json`.

## Wozu

Das Rig sagt, wo ein Körper koppeln **kann** — `contacts` in der Rig-Datei, Fersen, Zehen,
Griffpunkte. Es sagt nicht, was in einem bestimmten Clip tatsächlich gekoppelt **ist**.
Genau diese Lücke schließt der Kontaktplan: je Kontaktstelle die Frame-Spannen, in denen
sie eingerastet ist, und woran.

Zwei Dinge hängen daran, und beide sind ohne den Plan nicht sauber machbar:

**Retargeting.** Wer Gelenkwinkel eins zu eins auf einen anders proportionierten Körper
überträgt, bekommt Fußrutschen und Hände neben der Waffe. Die Winkel sind gar nicht die
Aussage der Bewegung — die Aussage ist, dass der Fuß auf dem Boden steht. Kontakte sind das
Invariante, Gelenkwinkel das Verhandelbare.

**Prüfung.** `cue.check_foot_slide` *rät* Kontakt aus „Fuß ist nah genug am Boden". Die
Prüfung ist damit nur so gut wie die Vermutung: ein Fuß, der absichtlich knapp über dem
Boden schwebt, wird fälschlich geprüft; ein rutschender Fuß auf einer Stufe gar nicht. Mit
Plan wird `check_contact_drift` eine Aussage statt einer Ahnung.

## Abgeleitet, dann eingecheckt

`combat.derive_phases()` ist bewusst eine **Ansicht** — Startup/Active/Recovery lassen sich
jederzeit neu berechnen, und sie zu speichern schüfe nur eine zweite Wahrheit, die veraltet.

Beim Kontaktplan ist es umgekehrt, und der Unterschied ist der Grund, warum das hier steht:
**er wird abgeleitet, dann eingecheckt, und ist ab dann die Wahrheit.**

Die Herleitung ist eine Heuristik — „am Boden, wenn nah genug dran". Eine Heuristik, die
jede Implementierung für sich neu rechnet, läuft auseinander. Dieselbe Klasse Fehler wie
`<` gegen `<=` beim Overlap-Test: beide Seiten halten sich für richtig, bis ein Fuß in der
einen Implementierung klebt und in der anderen rutscht. Und weil das Retargeting die
Kontakte als Invariante nimmt, überträgt eine anders geratene Herleitung schlicht eine
andere Bewegung.

`spar contacts <clip.glb>` erzeugt den Vorschlag. Was danach in der Datei steht, gilt.

## Kontaktarten

| Art | Bedeutung | Beispiel |
|---|---|---|
| `planted` | fixiert — der Weltpunkt darf sich nicht bewegen | Fuß am Boden |
| `sliding` | bleibt auf der Fläche, darf sich darauf bewegen | Schlittern, Rutschen |
| `pushing` | trägt Kraft, aber nur auf Druck | Faust am Kopf des Gegners |
| `carried` | folgt einem Objekt statt der Welt | Hand am Waffengriff |

Nur `planted` und `sliding` steuern das Retargeting; nur `planted` wird auf Drift geprüft
(bei `sliding` ist Bewegung ja die Absicht).

**Herleitbar ist allein `ground`.** Ob ein Fuß den Boden berührt, steht in der Geometrie. Ob
eine Hand eine Waffe hält, steht dort nicht — der Clip kennt das Objekt gar nicht. `carried`
und `pushing` müssen autoriert werden; sie zu raten hieße, Daten zu erfinden.

## Spannen sind inklusiv

`from` und `to` sind **beide inklusiv**. `[4, 4]` ist genau ein Frame.

Festgeschrieben, nicht Geschmack. Wer `to` exklusiv liest, verliert je Spanne den letzten
Frame — am Absprung genau den, der die Bewegung trägt. Ohne festgelegte Konvention wählt
eine Implementierung das eine und die nächste das andere.

→ `contact/spans-are-inclusive`

## Beispiel

```json
{
  "schema": "spar-contact/1",
  "clip": "jab",
  "rig": "biped/1",
  "frame_count": 7,
  "spans": [
    { "site": "heel_l", "kind": "planted", "from": 0, "to": 6,
      "target": { "type": "ground", "y": 0.0 } },
    { "site": "toe_l",  "kind": "planted", "from": 0, "to": 6,
      "target": { "type": "ground", "y": 0.0 } },
    { "site": "grip_r", "kind": "carried", "from": 0, "to": 6,
      "target": { "type": "prop", "id": "sword" } }
  ]
}
```

## Retargeting

`spar retarget <clip.glb> --to <rig-id>` überträgt bei **gleicher Topologie, anderen
Proportionen**. Übertragung zwischen verschiedenen Topologien braucht eine
Gliedmaßen-Zuordnung und ist ein eigenes Vorhaben.

Reihenfolge, und sie ist nicht beliebig:

1. Kontaktziele aus der Quelle merken.
2. **Root verschieben**, einmal, um das *Minimum* über alle eingerasteten Kontakte.
3. *Dann* je Kette die Zwei-Knochen-IK lösen.

Drei Punkte, an denen das schiefgeht und die deshalb Vektoren haben:

**Minimum, nicht Mittelwert.** Der Mittelwert lässt den tiefsten Kontakt unerreichbar, die
Kette fährt in die Streckung, das Bein überstreckt sichtbar.
→ `contact/root-shift-is-minimum`

**Die Verschiebung ist vorzeichenbehaftet.** Nur-Absenken ist die Annahme einer Figur auf
Gelände; beim Retargeting hebt ein langbeinigeres Ziel den Körper. Auf negative Werte
geklemmt bleibt es in der Hocke und alle Kontakte reißen ab.
→ `contact/retarget-hexapod`

**Reichweite geht mit ein, nicht nur die Höhendifferenz.** Nur die Höhe zu rechnen sieht
richtig aus und lässt bei kürzeren Gliedmaßen genau die fehlende Reichweite als Rest stehen
— der Fuß schwebt, das Bein ist gestreckt.
→ `contact/retarget-preserves-planted`

Dazu zwei Eigenschaften des Lösers selbst:

**Kontakte an einem Bone werden gemeinsam gelöst.** Ferse und Zehe hängen am selben Fuß.
Einzeln gelöst überschreibt die zweite die erste, keine sitzt richtig, und die Fußstellung
wird nie angefasst. Die Kette bringt die Gruppe hin, die Bone-Drehung legt sie flach.

**Die Ruhelage der Kette darf gebeugt sein.** Beim Biped zeigen Schienbein und Fuß beide
senkrecht nach unten, die Kette ruht gerade — ein Löser, der das voraussetzt, kommt damit
durch. Ein Insektenbein mit Femur nach außen-oben und Tibia nach außen-unten fällt sofort
auf. Deshalb rechnet der Löser mit dem *Innenwinkel* am Mittelgelenk und der Differenz zu
dessen Ruhewinkel, nicht mit „Beugung gegenüber gestreckt".
→ `contact/retarget-hexapod`
