# Determinismus-Regeln (verbindlich)

Zwei konforme Implementierungen in beliebigen Sprachen müssen bei gleichem Input
**bit-identische** Simulationsergebnisse liefern. Das ist mit Gleitkomma nicht erreichbar:
`sin`, `cos` und Quaternion-Normalisierung sind plattform- und
compilerabhängig, und volles 3D verschärft das gegenüber einem 2D-Winkelrig.

Die Lösung ist keine Fixed-Point-Mathematikbibliothek, sondern eine **Verlagerung**:
Gleitkomma darf existieren, aber nicht im Gameplay-Pfad.

## Die Trennung

| | Repräsentation | Wann berechnet |
|---|---|---|
| Skelett-FK, Rendern, Interpolation | Float | Laufzeit, jede Engine wie sie mag |
| Hitbox-Weltpositionen | **Fixed-Point Integer** | **Bake-Zeit, einmal** |
| Simulationszustand, Kollision, Treffer | **Integer** | Laufzeit, exakt |

Fighter-Clips sind vorautorisiert: Die Pose zu Frame *n* steht fest, bevor das Spiel
startet. Also wird die Welt-AABB jeder Box pro Frame **zur Bake-Zeit** ausgerechnet und als
Integer abgelegt. Die Runtime schlägt sie nach, verschiebt sie um die (ganzzahlige)
Kämpferposition und testet ganzzahlig auf Überlappung. Kein `sin`, kein Quaternion, kein
Rundungsverhalten im Gameplay-Pfad.

Preis: Posen, die zur Laufzeit prozedural verändert werden (IK, Ragdoll,
Aim-Offsets), können keine Gameplay-Boxen tragen. Für einen Fighter ist das kein Verlust —
framegenaue Autorenkontrolle ist dort ohnehin die Anforderung.

## Fixed-Point

```
UNIT_SCALE = 256          # Subunits pro Weltenheit
1 Weltenheit = 1 Meter    # Auflösung ≈ 3,9 mm
```

Umrechnung beim Bake, mit **Runden zur nächsten Ganzzahl, halbe Werte von Null weg**
(nicht Bankers Rounding — Python `round()` ist hier falsch):

```
to_fixed(v) = trunc(v * 256 + copysign(0.5, v))
```

Boxen werden **konservativ** gerundet: `min` abwärts, `max` aufwärts. Eine gebakene Box ist
damit nie kleiner als die exakte, und Treffer verschwinden nicht durch Rundung.

## Simulationszustand

Alle Felder ganzzahlig. Kein Float im Zustand, auch nicht als Zwischenwert:

- Position, Geschwindigkeit, Pushback: Subunits
- Frame-Zähler, Hitstun, Blockstun, Health: `int`
- Facing: `+1` oder `−1`

## RNG

Falls überhaupt nötig: xorshift128, hier festgelegt, damit alle Implementierungen dieselbe
Folge erzeugen. Niemals `random` / `Math.random` / `rand()` der Wirtssprache.

```
x ^= (x << 11) & 0xFFFFFFFF
x ^= x >> 8
x  = (w ^ (w >> 19)) ^ x
```

Zustand sind vier `uint32`. Der Seed gehört zum Input-Log.

## Replay

Ein Replay ist **Input-Log plus Seed**, nicht serialisierter Objektzustand. Derselbe Log auf
demselben Clip muss in jeder konformen Implementierung denselben Endzustand ergeben.

Das ist zugleich der schärfste Konformitätstest: Er prüft die gesamte Kette, nicht einzelne
Funktionen.
