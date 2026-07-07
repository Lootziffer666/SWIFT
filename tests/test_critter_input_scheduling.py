"""Tests for twin-stick input and human-readable NPC scheduling."""
import math
import os
import pytest
from core.critter.geometry import Vec2
from core.critter.input import TwinStickController
from core.critter.scheduling import NPCSchedule, ScheduleEntry
from core.critter.flow_field import FlowField, FlowFieldConfig, NPC


class TestTwinStick:
    def test_velocity_immediate(self):
        c = TwinStickController()
        c.set_movement(1.0, 0.0)
        v = c.velocity(speed=5.0)
        assert v.x == 5.0 and v.y == 0.0

    def test_no_movement_zero_velocity(self):
        c = TwinStickController()
        assert c.velocity(5.0) == Vec2(0, 0)

    def test_aim_decoupled_from_movement(self):
        c = TwinStickController()
        c.set_movement(0.0, 1.0)   # move "up"
        c.set_aim(1.0, 0.0)        # look "right"
        assert c.facing_angle() == 0.0
        assert c.velocity(1.0).y == 1.0

    def test_side_step_detected(self):
        c = TwinStickController()
        c.set_movement(1.0, 0.0)
        c.set_aim(0.0, 1.0)
        assert c.can_side_step() is True


class TestNPCSchedule:
    def test_parse_text(self):
        text = """
        # daily routine
        08:00 wake home
        12:00 eat market
        18:00 sleep home
        """
        sched = NPCSchedule.from_text(text)
        assert len(sched.entries) == 3
        assert sched.entries[0].action == "wake"

    def test_active_entry(self):
        sched = NPCSchedule.from_text("08:00 wake home\n12:00 eat market\n18:00 sleep home")
        assert sched.active_entry(9, 0).action == "wake"
        assert sched.active_entry(13, 30).action == "eat"
        assert sched.active_entry(20, 0).action == "sleep"

    def test_active_entry_before_first_is_none(self):
        sched = NPCSchedule.from_text("08:00 wake home")
        assert sched.active_entry(7, 0) is None

    def test_parse_file(self, tmp_path):
        p = tmp_path / "npc.txt"
        p.write_text("06:00 patrol gate\n22:00 rest barn")
        sched = NPCSchedule.from_file(str(p))
        assert sched.active_entry(23, 0).action == "rest"

    def test_route_to_low_power(self):
        sched = NPCSchedule.from_text("08:00 travel market")
        npc = NPC(id=1, x=0, y=0, on_screen=False)
        field = sched.route_to(npc, goal=(9, 0), grid_w=10, grid_h=1, speed=1.0, dt=1.0)
        assert isinstance(field, FlowField)
        assert npc.x > 0
