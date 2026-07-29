# Combat System Quick Start

## What is the Combat Engine?

SWIFT's Combat Engine is a **turn-based, simultaneous action system** that lets two fighters battle using strategic action selection. It includes:

- **4 action types**: Attack, Defend, Dodge, Wait
- **Probabilistic hit/miss system** with dodge and defense mechanics
- **Distance-based positioning** (Melee vs Range)
- **REST API** for programmatic access
- **Interactive web demo** at `/combat.html`

## Quick Demo

1. Start the SWIFT web server:
   ```bash
   python -m web.app
   ```

2. Open http://localhost:8000/combat.html

3. Click **"Neuer Kampf"** to start

4. Both players select actions simultaneously:
   - **⚔️ Attack**: Deal damage (70% base hit rate)
   - **🛡️ Defend**: Reduce damage by 50%, gain +20% dodge
   - **💨 Dodge**: Gain +60% dodge chance, attacks do 70% damage
   - **❤️ Wait**: Regenerate 10 HP

5. Turn executes when both select an action

6. Combat ends when one fighter reaches 0 HP

## Python API

### Start a Combat Session

```python
import requests

# Start a new combat
resp = requests.post('http://localhost:8000/api/combat/start', 
                     params={'fighter1': 'Hero', 'fighter2': 'Villain'})
session = resp.json()
session_id = session['session_id']
print(session['status'])  # Current combat state
```

### Execute a Turn

```python
# Fighter 0 attacks, Fighter 1 defends
resp = requests.post(f'http://localhost:8000/api/combat/action/{session_id}',
                     params={'fighter': 0, 'action': 'attack'})
# Response: {"waiting": true, "status": {...}}

resp = requests.post(f'http://localhost:8000/api/combat/action/{session_id}',
                     params={'fighter': 1, 'action': 'defend'})
# Response: {"turn": {...}, "status": {...}}  # Turn executed!
```

### Check Combat Status

```python
resp = requests.get(f'http://localhost:8000/api/combat/status/{session_id}')
status = resp.json()
print(status)
# {
#   "turn": 1,
#   "distance": 6.0,
#   "is_melee": false,
#   "fighter1": {...},
#   "fighter2": {...},
#   "is_over": false,
#   "winner": null
# }
```

### Reset Combat

```python
resp = requests.post(f'http://localhost:8000/api/combat/reset/{session_id}')
print(resp.json())  # Reset status
```

## JavaScript Example (Browser)

```javascript
let sessionId;

// Start combat
fetch('/api/combat/start?fighter1=Hero&fighter2=Villain', {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    sessionId = d.session_id;
    console.log('Combat started:', d.status);
  });

// Fighter 0 attacks
fetch(`/api/combat/action/${sessionId}?fighter=0&action=attack`, {method: 'POST'})
  .then(r => r.json())
  .then(d => console.log('Waiting for fighter 2...', d));

// Fighter 1 defends
fetch(`/api/combat/action/${sessionId}?fighter=1&action=defend`, {method: 'POST'})
  .then(r => r.json())
  .then(d => console.log('Turn executed!', d.turn, d.status));
```

## Action Details

### Attack ⚔️
- **Base Damage**: 25 + Variation (-5 to +5)
- **Hit Chance**: 70% - Defender's dodge chance
- **Range**: Up to 8 units away
- **Reduces to 70% damage if using Dodge**

**Hits reduce opponent's health.**

### Defend 🛡️
- **Damage Reduction**: -50% incoming damage
- **Dodge Bonus**: +20% evasion for this turn
- **Effect**: Passive — no offensive action

**Stacks with Defense stat for cumulative reduction.**

### Dodge 💨
- **Dodge Bonus**: +60% evasion chance
- **Damage Penalty**: Your attacks do 70% damage
- **Trade-off**: Offensive for defensive

**Good for avoiding big damage turns, but weakens your attacks.**

### Wait ❤️
- **Regeneration**: +10 HP
- **Max health**: Cannot exceed max_health
- **No combat effect**: No attack or defense bonus

**Use when low on health or to play passively.**

## Combat Mechanics

### Damage Formula

```
damage = (base_attack + variance) × (1 - defense_reduction) × (1 - damage_reduction)
```

Where:
- `base_attack` = Fighter's attack power (default: 25)
- `variance` = Random value -5 to +5
- `defense_reduction` = Target's defense stat effect
- `damage_reduction` = From DEFEND or other effects

### Hit Chance Formula

```
hit_chance = 0.70 - (opponent_dodge + dodge_bonus + defend_bonus)
hit_chance = clamp(hit_chance, 0.1, 0.95)
```

### Distance & Melee

- **Distance**: `|fighter1.position - fighter2.position|` (0-10 scale)
- **Melee Range**: < 2 units
- **Attack Range**: < 8 units

Fighters start at positions 2.0 and 8.0 (distance ≈ 6 units).

## Example Battle

```
TURN 1:
  Hero (pos=2) attacks → 20 damage
  Villain (pos=8) defends → Guard up
  Villain Health: 80/100

TURN 2:
  Hero waits → Regenerates 10 HP
  Villain attacks → 18 damage (50% reduced by defense)
  Hero Health: 92/100

TURN 3:
  Hero attacks → Hits! 24 damage
  Villain dodges → Misses!
  Villain Health: 56/100

... (continue until someone reaches 0 HP)

Winner: Hero!
```

## Extend the Combat System

### Add Custom Stats

```python
from core.combat_engine import CombatStats

class WarriorStats(CombatStats):
    max_health = 150
    attack_power = 35
    defense = 25
    dodge_chance = 0.05  # Less agile

class RogueStats(CombatStats):
    max_health = 70
    attack_power = 30
    defense = 5
    dodge_chance = 0.40  # Very agile
```

### Add Special Moves

```python
class ActionType(enum.Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    DODGE = "dodge"
    WAIT = "wait"
    POWER_ATTACK = "power_attack"  # 200% damage, next turn miss
    HEAL = "heal"                   # +30 HP, single use
```

### Custom Combat Rules

Modify `CombatEngine.execute_turn()` to add:
- **Status Effects** (Stunned, Bleeding, Fortified)
- **Multi-fighter combat** (3+ fighters)
- **Terrain effects** (Elevated ground, obstacles)
- **Special abilities** (Ultimate moves, combos)

## Testing

Run the test suite:

```bash
python tests/test_combat_engine.py
```

Output:
```
✓ Initialization test passed
✓ Basic attack test passed
✓ Dodge mechanic test passed
✓ Defend mechanic test passed
✓ Wait regeneration test passed
✓ Distance calculation test passed
✓ Range limits test passed
✓ Simultaneous actions test passed
✓ Combat ends test passed
✓ Status format test passed

✅ All combat engine tests passed!
```

## Next Steps

1. **Try the demo**: Go to `/combat.html`
2. **Read the detailed docs**: See `docs/COMBAT_MECHANICS.md`
3. **Integrate with SWIFT sprites**: Map combat animations to actions
4. **Add AI opponents**: Implement decision logic for non-player fighters
5. **Create battle scenarios**: Design tournament or campaign modes

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/combat/start` | Initialize new combat session |
| GET | `/api/combat/status/{id}` | Get current combat state |
| POST | `/api/combat/action/{id}` | Register and execute action |
| POST | `/api/combat/reset/{id}` | Reset combat to initial state |
| DELETE | `/api/combat/{id}` | Delete session (cleanup) |

See `docs/COMBAT_MECHANICS.md` for full API details.
