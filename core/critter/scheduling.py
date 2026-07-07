"""
Critter Crosser – NPC scheduling.

Daily routines are defined in human-readable text files (easy modding). Each
non-comment line is:

    HH:MM  <action>  <location>

The scheduler returns the active entry for a given time and can route an NPC
to a target level via a flow field, keeping the agent in low-power mode while
travelling between levels.
"""
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from core.critter.flow_field import FlowField, FlowFieldConfig, NPC


@dataclass
class ScheduleEntry:
    hour: int
    minute: int
    action: str
    location: str
    minutes: int  # sort key: hour*60 + minute

    @property
    def time_label(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"


class NPCSchedule:
    """
    Parse and query a human-readable schedule. Blank lines and lines starting
    with '#' are ignored.
    """

    def __init__(self, entries: Optional[List[ScheduleEntry]] = None):
        self.entries: List[ScheduleEntry] = sorted(
            entries or [], key=lambda e: e.minutes
        )

    @classmethod
    def from_text(cls, text: str) -> "NPCSchedule":
        entries: List[ScheduleEntry] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 3:
                continue
            time = parts[0]
            m = re.match(r"(\d{1,2}):(\d{2})", time)
            if not m:
                continue
            hour, minute = int(m.group(1)), int(m.group(2))
            action = parts[1]
            location = " ".join(parts[2:])
            entries.append(ScheduleEntry(hour, minute, action, location, hour * 60 + minute))
        return cls(entries)

    @classmethod
    def from_file(cls, path: str) -> "NPCSchedule":
        with open(path) as f:
            return cls.from_text(f.read())

    def active_entry(self, hour: int, minute: int) -> Optional[ScheduleEntry]:
        """Return the latest schedule entry whose time has passed."""
        now = hour * 60 + minute
        current: Optional[ScheduleEntry] = None
        for e in self.entries:
            if e.minutes <= now:
                current = e
            else:
                break
        return current

    def route_to(
        self,
        npc: NPC,
        goal: tuple,
        grid_w: int,
        grid_h: int,
        speed: float = 1.0,
        dt: float = 1.0,
    ) -> FlowField:
        """
        Build a flow field to `goal` and advance the NPC along it. While the
        NPC is off-screen the FlowField/NPC low-power mode skips heavy work.
        """
        cfg = FlowFieldConfig(width=grid_w, height=grid_h)
        field = FlowField(cfg)
        field.compute([goal])
        npc.on_screen = False  # travelling between levels -> low-power
        npc.update(field, speed, dt)
        return field
