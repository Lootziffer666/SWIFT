"""
Playable Combat Engine für SWIFT.

Unterstützt:
- Distance-basierte Positionen (Range, Melee)
- Action-Rotation (Beide spieler mit jeweils 3 Actions)
- Damage-Berechnung (Attack, Defence, Dodge)
- State-Tracking (Health, Position, Status Effects)
- Turn-System mit simultanen Aktionen
"""

import enum
import random
from dataclasses import dataclass, field
from typing import Optional


class ActionType(enum.Enum):
    """Verfügbare Aktionstypen."""
    ATTACK = "attack"      # Aggressive Aktion: 70% Hit, 25 Schaden
    DEFEND = "defend"      # Defensive Aktion: -50% Damage (nächsten Turn), +20% Counterattack
    DODGE = "dodge"        # Evasion: +60% Ausweich-Chance, -30% eigener Damage
    WAIT = "wait"          # Neutral: Regeneration 10 HP


@dataclass
class CombatStats:
    """Charakteristische Stats für Kampf."""
    max_health: int = 100
    current_health: int = field(init=False)
    attack_power: int = 25          # Base damage
    defense: int = 15               # Damage reduction
    dodge_chance: float = 0.15       # Base dodge %

    def __post_init__(self):
        self.current_health = self.max_health


@dataclass
class CombatState:
    """State eines Charakters im Kampf."""
    name: str
    stats: CombatStats
    position: float = 5.0           # 0-10 scale, mitte=5
    last_action: Optional[ActionType] = None
    defending: bool = False          # Wurde verteidigt im letzten Turn?
    dodge_bonus: float = 0.0         # Zusätzliche Dodge-Chance
    damage_reduction: float = 0.0    # Damage Reduction %
    is_stunned: bool = False

    @property
    def is_alive(self) -> bool:
        return self.stats.current_health > 0

    @property
    def health_percent(self) -> float:
        return max(0, self.stats.current_health / self.stats.max_health)


class CombatEngine:
    """
    Turn-basiertes Kampfsystem mit simultanen Aktionen.

    Beispiel:
        engine = CombatEngine()
        engine.set_action(0, ActionType.ATTACK)
        engine.set_action(1, ActionType.DEFEND)
        results = engine.execute_turn()
    """

    def __init__(self, fighter1_name: str = "Fighter 1", fighter2_name: str = "Fighter 2"):
        self.fighter1 = CombatState(
            name=fighter1_name,
            stats=CombatStats(),
            position=2.0  # Links
        )
        self.fighter2 = CombatState(
            name=fighter2_name,
            stats=CombatStats(),
            position=8.0  # Rechts
        )
        self.current_turn = 0
        self.pending_actions = [None, None]
        self.turn_log = []

    def get_distance(self) -> float:
        """Distanz zwischen Kämpfern (0-10 scale)."""
        return abs(self.fighter1.position - self.fighter2.position)

    def is_melee_range(self) -> bool:
        """Sind Kämpfer in Melee-Range (< 2 Einheiten)?"""
        return self.get_distance() < 2.0

    def is_in_range(self, action_type: ActionType) -> bool:
        """Kann die Aktion ausgeführt werden (Range-Check)?"""
        distance = self.get_distance()
        if action_type == ActionType.ATTACK:
            return distance < 8.0  # Max Attack Range
        return True  # Andere Aktionen haben keine Range-Limits

    def set_action(self, fighter_idx: int, action: ActionType) -> bool:
        """Registriere eine Aktion für einen Kämpfer (vor execute_turn)."""
        if fighter_idx not in [0, 1]:
            raise ValueError("fighter_idx must be 0 or 1")
        if not self.is_in_range(action):
            return False
        self.pending_actions[fighter_idx] = action
        return True

    def calculate_hit_chance(self, attacker: CombatState, defender: CombatState) -> float:
        """Berechne Hit-Chance für einen Angriff."""
        base_hit = 0.70

        # Defender-Dodge wird berücksichtigt
        defender_dodge = defender.stats.dodge_chance + defender.dodge_bonus
        if defender.defending:
            defender_dodge += 0.20  # Defend gibt +20% Dodge

        return max(0.1, min(0.95, base_hit - defender_dodge))

    def apply_damage(self, attacker: CombatState, defender: CombatState, base_damage: int) -> int:
        """Berechne und wende Schaden an."""
        # Hit-Check
        hit_chance = self.calculate_hit_chance(attacker, defender)
        if random.random() > hit_chance:
            return 0  # MISS!

        # Schaden-Berechnung
        damage = base_damage + random.randint(-5, 5)  # Variance

        # Defense reduziert Schaden
        defense_reduction = min(0.5, defender.stats.defense / 100)
        damage = int(damage * (1 - defense_reduction))

        # Damage Reduction (z.B. von DEFEND)
        damage = int(damage * (1 - defender.damage_reduction))

        # Mindestschaden
        damage = max(1, damage)

        defender.stats.current_health -= damage
        return damage

    def move_towards(self, fighter: CombatState, other: CombatState, distance: float = 1.0):
        """Bewege Kämpfer näher zum Gegner."""
        if fighter.position < other.position:
            fighter.position = min(fighter.position + distance, other.position - 0.5)
        else:
            fighter.position = max(fighter.position - distance, other.position + 0.5)

    def move_away(self, fighter: CombatState, distance: float = 1.0):
        """Bewege Kämpfer weg (Richtung Spielfeldrand)."""
        if fighter.position < 5:
            fighter.position = max(0, fighter.position - distance)
        else:
            fighter.position = min(10, fighter.position + distance)

    def execute_turn(self) -> dict:
        """
        Führe einen Kampf-Turn aus mit simultanen Aktionen beider Kämpfer.
        Gibt Turn-Ergebnis mit Events zurück.
        """
        self.current_turn += 1

        # Validiere ausstehende Aktionen
        if self.pending_actions[0] is None or self.pending_actions[1] is None:
            raise ValueError("Beide Kämpfer müssen eine Aktion gesetzt haben")

        action1 = self.pending_actions[0]
        action2 = self.pending_actions[1]
        self.pending_actions = [None, None]

        events = []

        # Reset Status
        self.fighter1.defending = False
        self.fighter2.defending = False
        self.fighter1.damage_reduction = 0.0
        self.fighter2.damage_reduction = 0.0
        self.fighter1.dodge_bonus = 0.0
        self.fighter2.dodge_bonus = 0.0

        # 1. Verarbeite DEFEND-Aktionen (erhöhen Dodge/Reduction)
        if action1 == ActionType.DEFEND:
            self.fighter1.defending = True
            self.fighter1.damage_reduction = 0.50
            self.fighter1.dodge_bonus = 0.20
            events.append({"fighter": 0, "type": "defend", "msg": "Guard aufgestellt!"})

        if action2 == ActionType.DEFEND:
            self.fighter2.defending = True
            self.fighter2.damage_reduction = 0.50
            self.fighter2.dodge_bonus = 0.20
            events.append({"fighter": 1, "type": "defend", "msg": "Guard aufgestellt!"})

        # 2. Verarbeite DODGE-Aktionen (erhöhen Dodge, reduzieren Angriff)
        if action1 == ActionType.DODGE:
            self.fighter1.dodge_bonus = 0.60
            events.append({"fighter": 0, "type": "dodge", "msg": "Evasion-Pose!"})
            # Dodge reduziert auch den eigenen Schaden
            action1_is_dodge = True
        else:
            action1_is_dodge = False

        if action2 == ActionType.DODGE:
            self.fighter2.dodge_bonus = 0.60
            events.append({"fighter": 1, "type": "dodge", "msg": "Evasion-Pose!"})
            action2_is_dodge = True
        else:
            action2_is_dodge = False

        # 3. Verarbeite WAIT-Aktionen (Regeneration)
        if action1 == ActionType.WAIT:
            heal_amount = 10
            self.fighter1.stats.current_health = min(
                self.fighter1.stats.max_health,
                self.fighter1.stats.current_health + heal_amount
            )
            events.append({"fighter": 0, "type": "wait", "msg": f"Regeneriert {heal_amount} HP", "heal": heal_amount})

        if action2 == ActionType.WAIT:
            heal_amount = 10
            self.fighter2.stats.current_health = min(
                self.fighter2.stats.max_health,
                self.fighter2.stats.current_health + heal_amount
            )
            events.append({"fighter": 1, "type": "wait", "msg": f"Regeneriert {heal_amount} HP", "heal": heal_amount})

        # 4. Verarbeite ATTACK-Aktionen (simultane Angriffe)
        if action1 == ActionType.ATTACK and self.is_in_range(action1):
            self.fighter1.last_action = action1
            base_damage = self.fighter1.stats.attack_power
            if action1_is_dodge:
                base_damage = int(base_damage * 0.7)  # Dodge reduziert Angriff

            damage = self.apply_damage(self.fighter1, self.fighter2, base_damage)
            if damage > 0:
                events.append({
                    "fighter": 0,
                    "type": "attack",
                    "hit": True,
                    "damage": damage,
                    "msg": f"Angriff trifft! {damage} Schaden",
                })
            else:
                events.append({
                    "fighter": 0,
                    "type": "attack",
                    "hit": False,
                    "msg": "Angriff wird ausgewichen!",
                })

        if action2 == ActionType.ATTACK and self.is_in_range(action2):
            self.fighter2.last_action = action2
            base_damage = self.fighter2.stats.attack_power
            if action2_is_dodge:
                base_damage = int(base_damage * 0.7)  # Dodge reduziert Angriff

            damage = self.apply_damage(self.fighter2, self.fighter1, base_damage)
            if damage > 0:
                events.append({
                    "fighter": 1,
                    "type": "attack",
                    "hit": True,
                    "damage": damage,
                    "msg": f"Angriff trifft! {damage} Schaden",
                })
            else:
                events.append({
                    "fighter": 1,
                    "type": "attack",
                    "hit": False,
                    "msg": "Angriff wird ausgewichen!",
                })

        # 5. Store turn log
        turn_data = {
            "turn": self.current_turn,
            "distance": self.get_distance(),
            "fighter1": {
                "action": action1.value,
                "health": self.fighter1.stats.current_health,
                "position": self.fighter1.position,
            },
            "fighter2": {
                "action": action2.value,
                "health": self.fighter2.stats.current_health,
                "position": self.fighter2.position,
            },
            "events": events,
        }
        self.turn_log.append(turn_data)

        return turn_data

    def reset(self):
        """Setze Kampf zurück."""
        self.__init__(self.fighter1.name, self.fighter2.name)

    def get_status(self) -> dict:
        """Gib aktuellen Kampf-Status zurück."""
        return {
            "turn": self.current_turn,
            "distance": self.get_distance(),
            "is_melee": self.is_melee_range(),
            "fighter1": {
                "name": self.fighter1.name,
                "health": self.fighter1.stats.current_health,
                "max_health": self.fighter1.stats.max_health,
                "health_percent": self.fighter1.health_percent,
                "position": self.fighter1.position,
                "alive": self.fighter1.is_alive,
                "last_action": self.fighter1.last_action.value if self.fighter1.last_action else None,
            },
            "fighter2": {
                "name": self.fighter2.name,
                "health": self.fighter2.stats.current_health,
                "max_health": self.fighter2.stats.max_health,
                "health_percent": self.fighter2.health_percent,
                "position": self.fighter2.position,
                "alive": self.fighter2.is_alive,
                "last_action": self.fighter2.last_action.value if self.fighter2.last_action else None,
            },
            "is_over": not (self.fighter1.is_alive and self.fighter2.is_alive),
            "winner": (
                self.fighter1.name if self.fighter1.is_alive and not self.fighter2.is_alive
                else self.fighter2.name if self.fighter2.is_alive and not self.fighter1.is_alive
                else None
            ),
        }
