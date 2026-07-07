"""Tests for flow-field pathfinding, tile costs and low-power NPCs."""
import numpy as np
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC


class TestFlowField:
    def test_reaches_goal_backwards(self):
        cfg = FlowFieldConfig(width=10, height=1)
        f = FlowField(cfg)
        f.compute([(9, 0)])  # goal at far right
        # Integration values should increase with distance from goal.
        assert f.integration[0, 9] == 0.0
        assert f.integration[0, 0] > f.integration[0, 5]
        # Vector at tile 0 should point right (+x) toward goal.
        d = f.direction_at(0, 0)
        assert d.x == 1.0

    def test_blocked_tiles_avoided(self):
        cfg = FlowFieldConfig(width=5, height=3)
        f = FlowField(cfg)
        # Wall down the middle column.
        for y in range(3):
            f.set_blocked(2, y)
        f.compute([(4, 1)])
        # No flow vector should ever point into a blocked tile.
        for y in range(3):
            d = f.direction_at(1, y)
            assert not (d.x == 1.0 and d.y == 0.0) or (1 + 1) >= 5

    def test_tile_costs_bias_routing(self):
        # Make the direct middle tile a costly "street" so the field must
        # detour through the cheap "sidewalk" tiles instead.
        cfg = FlowFieldConfig(width=3, height=3)
        f = FlowField(cfg)
        f.set_cost(1, 1, 100)  # street in the centre
        f.compute([(2, 1)])
        # From (0,1) the cheap path detours via row 2: 1+1+1+1 = 4.
        assert f.integration[0, 1] <= 4.0 + 1e-3
        # The costly straight-through route (1+100+1) must NOT be chosen.
        assert f.integration[0, 1] < 50.0

    def test_one_byte_per_tile(self):
        cfg = FlowFieldConfig(width=64, height=64)
        f = FlowField(cfg)
        assert f.memory_bytes() == 64 * 64


class TestNPCLowPower:
    def test_offscreen_skips_state_machine(self):
        cfg = FlowFieldConfig(width=10, height=1)
        f = FlowField(cfg)
        f.compute([(9, 0)])
        npc = NPC(id=1, x=0, y=0, on_screen=False)
        npc.update(f, speed=1.0, dt=1.0)
        assert npc.x > 0  # still moved via flow field
        assert npc.state == "idle"  # state machine untouched in low-power

    def test_onscreen_runs_state_machine(self):
        cfg = FlowFieldConfig(width=10, height=1)
        f = FlowField(cfg)
        f.compute([(9, 0)])
        npc = NPC(id=2, x=0, y=0, on_screen=True)
        npc.update(f, speed=1.0, dt=1.0)
        assert npc.state == "moving"
