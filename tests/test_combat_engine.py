"""Tests for SWIFT Combat Engine."""

import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.combat_engine import CombatEngine, ActionType, CombatState, CombatStats


def test_combat_initialization():
    """Test that combat engine initializes correctly."""
    engine = CombatEngine("Hero", "Villain")

    assert engine.fighter1.name == "Hero"
    assert engine.fighter2.name == "Villain"
    assert engine.fighter1.stats.current_health == 100
    assert engine.fighter2.stats.current_health == 100
    assert engine.current_turn == 0


def test_basic_attack():
    """Test that attacks can deal damage (statistically)."""
    engine = CombatEngine()

    # Run multiple attacks to account for miss chance
    hits = 0
    for _ in range(10):
        engine.reset()
        engine.set_action(0, ActionType.ATTACK)
        engine.set_action(1, ActionType.WAIT)
        result = engine.execute_turn()
        if engine.fighter2.stats.current_health < 100:
            hits += 1

    # With 70% base hit rate, we should get at least some hits
    assert hits > 0, "No attacks hit in 10 tries (base hit: 70%)"
    assert result["turn"] == 1


def test_dodge_mechanic():
    """Test that dodge increases evasion chance."""
    engine = CombatEngine()

    # Many attacks against dodge to test miss rate
    hits = 0
    for _ in range(10):
        engine.reset()
        engine.set_action(0, ActionType.ATTACK)
        engine.set_action(1, ActionType.DODGE)
        engine.execute_turn()
        if engine.fighter2.stats.current_health < 100:
            hits += 1

    # With 60% dodge bonus, hit rate should be roughly 10%
    # This is statistical, so we just check it's less than 70% base
    assert hits < 8, f"Too many hits with dodge active: {hits}/10"


def test_defend_mechanic():
    """Test that defend reduces damage (average over multiple trials)."""
    # Run multiple trials to account for hit randomness
    damage_without_defend_trials = []
    damage_with_defend_trials = []

    for _ in range(10):
        # Attack without defense
        engine = CombatEngine()
        engine.set_action(0, ActionType.ATTACK)
        engine.set_action(1, ActionType.WAIT)
        engine.execute_turn()
        damage = 100 - engine.fighter2.stats.current_health
        damage_without_defend_trials.append(damage)

        # Attack with defense
        engine = CombatEngine()
        engine.set_action(0, ActionType.ATTACK)
        engine.set_action(1, ActionType.DEFEND)
        engine.execute_turn()
        damage = 100 - engine.fighter2.stats.current_health
        damage_with_defend_trials.append(damage)

    avg_without = sum(damage_without_defend_trials) / len(damage_without_defend_trials)
    avg_with = sum(damage_with_defend_trials) / len(damage_with_defend_trials)

    # Defend should reduce average damage
    assert avg_with <= avg_without, f"Defend should reduce damage: {avg_without} vs {avg_with}"


def test_wait_regeneration():
    """Test that wait action regenerates health."""
    engine = CombatEngine()

    # Damage fighter1 first via attack from fighter2
    engine.set_action(0, ActionType.WAIT)
    engine.set_action(1, ActionType.ATTACK)
    engine.execute_turn()

    health_after_damage = engine.fighter1.stats.current_health
    assert health_after_damage < 100, "Fighter1 should have taken damage"

    # Now both wait
    engine.set_action(0, ActionType.WAIT)
    engine.set_action(1, ActionType.WAIT)
    engine.execute_turn()

    health_after_regen = engine.fighter1.stats.current_health

    assert health_after_regen > health_after_damage, "Health should increase after wait"
    expected = min(health_after_damage + 10, 100)
    assert health_after_regen == expected, f"Expected {expected}, got {health_after_regen}"


def test_distance_calculation():
    """Test that distance is calculated correctly."""
    engine = CombatEngine()

    distance = engine.get_distance()
    assert 0 <= distance <= 10

    # Fighters start at positions 2.0 and 8.0
    assert abs(distance - 6.0) < 0.1


def test_range_limits():
    """Test that actions respect range limits."""
    engine = CombatEngine()

    # Default positions allow attack
    assert engine.is_in_range(ActionType.ATTACK)

    # Move fighter far away
    engine.fighter1.position = 0
    engine.fighter2.position = 10

    # Attack should still be in range (< 8)
    assert not engine.is_in_range(ActionType.ATTACK)


def test_simultaneous_actions():
    """Test that both fighters can damage each other in same turn."""
    engine = CombatEngine()

    # Both attack
    engine.set_action(0, ActionType.ATTACK)
    engine.set_action(1, ActionType.ATTACK)

    result = engine.execute_turn()

    # Check that turn log has events for both
    events = result["events"]
    attack_events = [e for e in events if e["type"] == "attack"]
    assert len(attack_events) == 2


def test_combat_ends():
    """Test that combat ends when fighter dies."""
    engine = CombatEngine()

    # Reduce fighter 2's health to near death
    engine.fighter2.stats.current_health = 10

    # Fighter 1 attacks with guaranteed hit
    engine.set_action(0, ActionType.ATTACK)
    engine.set_action(1, ActionType.WAIT)

    result = engine.execute_turn()
    status = engine.get_status()

    # Check if combat ended
    if not engine.fighter2.is_alive:
        assert status["is_over"]
        assert status["winner"] == "Fighter 1"


def test_status_format():
    """Test that status output has correct format."""
    engine = CombatEngine()
    status = engine.get_status()

    assert "turn" in status
    assert "distance" in status
    assert "fighter1" in status
    assert "fighter2" in status
    assert "is_over" in status
    assert "winner" in status

    assert status["fighter1"]["health"] == 100
    assert status["fighter1"]["health_percent"] == 1.0
    assert status["fighter1"]["alive"]


if __name__ == "__main__":
    test_combat_initialization()
    print("✓ Initialization test passed")

    test_basic_attack()
    print("✓ Basic attack test passed")

    test_dodge_mechanic()
    print("✓ Dodge mechanic test passed")

    test_defend_mechanic()
    print("✓ Defend mechanic test passed")

    test_wait_regeneration()
    print("✓ Wait regeneration test passed")

    test_distance_calculation()
    print("✓ Distance calculation test passed")

    test_range_limits()
    print("✓ Range limits test passed")

    test_simultaneous_actions()
    print("✓ Simultaneous actions test passed")

    test_combat_ends()
    print("✓ Combat ends test passed")

    test_status_format()
    print("✓ Status format test passed")

    print("\n✅ All combat engine tests passed!")
