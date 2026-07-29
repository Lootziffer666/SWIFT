# SWIFT Combat Engine · Playable Fight Mechanics

## Übersicht

Das **SWIFT Combat Engine** ist ein turn-basiertes, simultanes Kampfsystem, das zwei Kämpfer in einer Arena konfrontiert. Es verbindet strategische Aktion-Auswahl mit Wahrscheinlichkeitsberechnungen für Treffer, Ausweichen und Schaden.

### Design-Prinzipien

1. **Simultane Aktionen**: Beide Kämpfer wählen ihre Aktionen gleichzeitig. Keine Zugserie — alle Effekte gelten für denselben Turn.
2. **Einfache, tiefe Mechaniken**: Nur 4 Basis-Aktionstypen, aber jede interagiert mit komplexen Damage/Defense-Formeln.
3. **Positionierung & Distanz**: Kämpfer haben eine Position (0-10 Scale), Angriffe haben Range-Limits.
4. **Wahrscheinlichkeitsbasis**: Hit-Chancen werden basierend auf Angreifer-Offensiv + Verteidiger-Defensiv berechnet.

---

## Aktion-Typen

### 1. ATTACK ⚔️
**Offensiv-Aktion**. Versucht, den Gegner zu treffen.

- **Hit-Chance**: 70% Base, minus Gegner-Dodge-Chancen
- **Damage**: 25 Base + Variation (-5 bis +5)
- **Range**: Max 8 Einheiten (aus Ferne möglich)
- **Effekt bei DODGE**: Angriff wird auf 70% des Schadens reduziert

**Wahrscheinlichkeitsformel**:
```
hit_chance = 0.70 - (gegner.dodge_chance + gegner.dodge_bonus + gegner.defend_bonus)
```

### 2. DEFEND 🛡️
**Defensive Aktion**. Verstärkt Abwehr für diesen Turn.

- **Damage Reduction**: -50% eingehender Schaden
- **Dodge Bonus**: +20% Ausweich-Chance
- **Gegeneffekt**: Kann nicht angreifen; nur passiv

**Effekt**:
```
damage_reduction = 0.50
dodge_bonus = 0.20
```

### 3. DODGE 💨
**Evasion-Aktion**. Fokus auf Ausweichbewegungen.

- **Dodge Bonus**: +60% Ausweich-Chance
- **Damage Reduction**: Eigene Angriffe tun nur 70% Schaden
- **Trade-off**: Offensive für Defensive

**Effekt**:
```
dodge_bonus = 0.60
angriff_damage = base_damage * 0.7
```

### 4. WAIT ❤️
**Neutral-Aktion**. Zeit nehmen zum Heilen.

- **Regeneration**: +10 HP
- **Kein Angriff oder Abwehr**: Defensive und offensive Boni sind 0

**Effekt**:
```
health += 10 (max: max_health)
```

---

## Kampf-Mechaniken

### Schaden-Berechnung

```python
def apply_damage(attacker, defender, base_damage):
    # 1. Hit-Chance Check
    if random() > calculate_hit_chance(attacker, defender):
        return 0  # MISS!

    # 2. Schaden mit Varianz
    damage = base_damage + randint(-5, 5)

    # 3. Defense-Reduktion
    defense_reduction = min(0.5, defender.defense / 100)
    damage = damage * (1 - defense_reduction)

    # 4. Damage Reduction (von DEFEND)
    damage = damage * (1 - defender.damage_reduction)

    # 5. Mindestschaden
    damage = max(1, damage)

    return damage
```

### Distanz & Range

Kämpfer haben eine Position auf einer **0-10 Scale**:
- **Position 0-2**: Linker Rand
- **Position 5**: Mittelpunkt
- **Position 8-10**: Rechter Rand

**Distanz** = `|fighter1.position - fighter2.position|`

**Range-Checks**:
- ATTACK: Max 8 Einheiten (kann aus der Ferne angreifen)
- Andere Aktionen: Keine Limits

**Melee-Range**: < 2 Einheiten (nah beim Gegner)

### Turn-Verarbeitung

Ein **Turn** läuft in dieser Reihenfolge ab:

1. **DEFEND-Aktionen verarbeiten** (setze Bonus)
2. **DODGE-Aktionen verarbeiten** (setze Bonus, reduziere Angriff)
3. **WAIT-Aktionen verarbeiten** (Regeneration)
4. **ATTACK-Aktionen verarbeiten** (simultane Angriffe)
5. **Log & Status aktualisieren**

Beide Kämpfer führen ATTACK gleichzeitig aus — kein Counter-Hit System.

---

## Charakter-Stats

Jeder Kämpfer hat folgende Base-Stats:

```python
@dataclass
class CombatStats:
    max_health: int = 100
    current_health: int = 100
    attack_power: int = 25         # Base Angriff-Schaden
    defense: int = 15              # Damage Reduction %
    dodge_chance: float = 0.15      # Base Ausweich-Chance (15%)
```

Diese können für unterschiedliche Charakter-Archetypen variiert werden:
- **Krieger**: Hohe Health, hohe Attack, niedrige Dodge
- **Schurke**: Niedrige Health, hohe Dodge, mittlere Attack
- **Paladin**: Hohe Health, hohe Defense, niedrige Dodge

---

## API-Schnittstellen

### POST `/api/combat/start`
Starte eine neue Kampf-Session.

**Query-Parameter**:
- `fighter1` (optional): Name von Kämpfer 1 (default: "Fighter 1")
- `fighter2` (optional): Name von Kämpfer 2 (default: "Fighter 2")

**Response**:
```json
{
  "session_id": "a3f7c9d2...",
  "status": { /* siehe GET /api/combat/status */ }
}
```

### GET `/api/combat/status/{session_id}`
Gib aktuellen Kampf-Status.

**Response**:
```json
{
  "turn": 1,
  "distance": 5.2,
  "is_melee": false,
  "fighter1": {
    "name": "Held",
    "health": 100,
    "max_health": 100,
    "health_percent": 1.0,
    "position": 2.0,
    "alive": true,
    "last_action": null
  },
  "fighter2": { /* ... */ },
  "is_over": false,
  "winner": null
}
```

### POST `/api/combat/action/{session_id}`
Registriere eine Aktion für einen Kämpfer und führe ggf. Turn aus.

**Query-Parameter**:
- `fighter` (int): 0 oder 1
- `action` (string): "attack", "defend", "dodge", "wait"

**Response**:
Wenn beide Kämpfer bereit sind:
```json
{
  "turn": {
    "turn": 1,
    "distance": 5.2,
    "fighter1": { "action": "attack", "health": 92, "position": 2.0 },
    "fighter2": { "action": "defend", "health": 100, "position": 8.0 },
    "events": [
      {
        "fighter": 0,
        "type": "attack",
        "hit": true,
        "damage": 20,
        "msg": "Angriff trifft! 20 Schaden"
      },
      {
        "fighter": 1,
        "type": "defend",
        "msg": "Guard aufgestellt!"
      }
    ]
  },
  "status": { /* siehe GET /api/combat/status */ }
}
```

Wenn noch nicht beide bereit:
```json
{
  "waiting": true,
  "status": { /* aktuelle Status */ }
}
```

### POST `/api/combat/reset/{session_id}`
Setze Kampf zurück auf Ausgangszustand.

### DELETE `/api/combat/{session_id}`
Lösche eine Kampf-Session.

---

## Beispiel-Ablauf

```
TURN 1:
  Fighter 1 (Held): wählt ATTACK
  Fighter 2 (Gegner): wählt DEFEND

  Events:
    - Fighter 1 greift an → trifft für 20 Schaden
    - Fighter 2 setzt Guard auf → Damage Reduction aktiv

TURN 2:
  Fighter 1: wählt DODGE
  Fighter 2: wählt ATTACK

  Events:
    - Fighter 1 weicht aus → +60% Dodge-Chance
    - Fighter 2 greift an → verfehlt (wegen Dodge)

TURN 3:
  Fighter 1: wählt WAIT
  Fighter 2: wählt ATTACK

  Events:
    - Fighter 1 regeneriert 10 HP
    - Fighter 2 greift an → trifft für 15 Schaden

... Kampf läuft bis ein Kämpfer Health = 0 hat.
```

---

## Web-Demo (combat.html)

Die interaktive Demo unter `/combat.html` zeigt:

1. **Battlefield-Visualisierung**: Zwei Kämpfer-Positionen auf einer Bühne
2. **Health-Bars**: Mit Prozent-Anzeige und numerischem Wert
3. **Action-Buttons**: Vier Buttons pro Kämpfer für jede Aktion
4. **Turn-Log**: Live-Ausgabe aller Events und Damage-Zahlen
5. **Simultane Auswahl**: Beide Kämpfer wählen, dann führe Turn aus

**Ablauf**:
1. Klick „Neuer Kampf"
2. Spieler 1 wählt eine Aktion (Button wird hervorgehoben)
3. Spieler 2 wählt eine Aktion
4. Turn wird sofort ausgeführt, Events werden geloggt
5. Wiederhole bis ein Kämpfer besiegt ist

---

## Erweiterungsmöglichkeiten

### 1. Charakter-Archetypen
```python
class Warrior(CombatStats):
    max_health = 150
    attack_power = 35
    defense = 25
    dodge_chance = 0.05

class Rogue(CombatStats):
    max_health = 70
    attack_power = 30
    defense = 5
    dodge_chance = 0.35
```

### 2. Special Moves / Ultimate-Aktionen
```
POWER_ATTACK: 150% Schaden, aber nächster Turn verloren
HEAL: +30 HP, nur 1x pro Kampf einsetzbar
COUNTER: Pariere nächsten Angriff und mache Gegenschaden
```

### 3. Status-Effekte
```
STUNNED: Kann diese Runde nicht agieren
BLEEDING: Verliert 5 HP pro Turn (3 Turns)
FORTIFIED: Verstärkte Defense (2 Turns)
```

### 4. Multi-Fighter Kampf (1v1v1, 2v2)
Erweitere `CombatEngine` um beliebig viele Kämpfer statt nur 2.

### 5. Positionen & Formationen
Erweitere Position auf 2D-Grid für taktischere Positionierung.

---

## Implementierungs-Architektur

- **Backend**: `core/combat_engine.py` — Pure Python, keine Abhängigkeiten
- **API**: `web/app.py` — FastAPI Endpoints
- **Frontend**: `web/static/combat.html` — Vanilla JS mit Canvas/CSS
- **Integration**: Kann direkt mit SWIFT Sprite-Sheets gekoppelt werden (Sprite-Anima­tionen als Kampf-Frames)

