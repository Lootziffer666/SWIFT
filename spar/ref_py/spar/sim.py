"""Deterministische Kampfsimulation.

Ausschliesslich Ganzzahlarithmetik. Kein Float taucht hier auf, auch nicht als
Zwischenwert -- die Weltraum-Hitboxen liegen bereits als Fixed-Point-Integer im
``fcd-baked/1``-Dokument (siehe ``bake.py``), und Positionen sind Subunits.

Damit ist der komplette Gameplay-Pfad frei von ``sin``, Quaternionen und
plattformabhaengigem Rundungsverhalten. Zwei Implementierungen in verschiedenen Sprachen
liefern bit-identische Ergebnisse -- das ist die Eigenschaft, die die Conformance-Suite
prueft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

# Input-Bits
IN_LEFT = 1
IN_RIGHT = 2
IN_ATTACK = 4
IN_BLOCK = 8


class State(IntEnum):
    IDLE = 0
    WALK = 1
    ATTACK = 2
    HITSTUN = 3
    BLOCKSTUN = 4


@dataclass
class Ruleset:
    """Globale Regeln. Alles ganzzahlig, alles Teil des Conformance-Vertrags."""

    max_health: int = 100
    walk_speed: int = 6
    """Subunits pro Frame (~1,4 m/s bei 60 fps)."""
    stage_min: int = -1536  # -6 m
    stage_max: int = 1536  # +6 m
    push_apart: int = 96
    """Mindestabstand der Kaempfer in Subunits (Pushbox-Ersatz)."""


@dataclass
class Fighter:
    name: str
    moves: dict[str, dict]
    """Tag -> ``fcd-baked/1``-Dokument."""
    x: int = 0
    facing: int = 1
    health: int = 100
    state: State = State.IDLE
    move_tag: str | None = None
    move_frame: int = 0
    stun: int = 0
    blocking: bool = False
    """Haelt der Kaempfer in diesem Frame Block. Wird in ``_advance`` aus dem Input
    gesetzt und in ``_resolve_hits`` gelesen -- Treffer werden nach beiden Kaempfern
    aufgeloest, damit die Auswertungsreihenfolge das Ergebnis nicht beeinflusst."""
    hit_ids: set[str] = field(default_factory=set)
    """Bereits gelandete Boxen dieses Moves -- verhindert Mehrfachtreffer pro Aktivphase."""

    @property
    def alive(self) -> bool:
        return self.health > 0

    def current_frame_data(self) -> dict | None:
        if self.move_tag is None:
            return None
        doc = self.moves[self.move_tag]
        if self.move_frame >= len(doc["frames"]):
            return None
        return doc["frames"][self.move_frame]

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "x": self.x,
            "facing": self.facing,
            "health": self.health,
            "state": int(self.state),
            "move": self.move_tag,
            "move_frame": self.move_frame,
            "stun": self.stun,
        }


@dataclass
class Event:
    frame: int
    kind: str  # "hit" | "block" | "move_start" | "move_end" | "ko"
    source: str
    target: str | None = None
    damage: int = 0

    def to_dict(self) -> dict:
        d = {"frame": self.frame, "kind": self.kind, "source": self.source}
        if self.target is not None:
            d["target"] = self.target
        if self.damage:
            d["damage"] = self.damage
        return d


class Sim:
    """Framegenaue Simulation zweier Kaempfer."""

    def __init__(self, a: Fighter, b: Fighter, rules: Ruleset | None = None) -> None:
        self.rules = rules or Ruleset()
        self.a = a
        self.b = b
        self.frame = 0
        self.events: list[Event] = []
        for f in (a, b):
            f.health = self.rules.max_health

    # ------------------------------------------------------------- Schritt

    def step(self, input_a: int, input_b: int) -> list[Event]:
        """Ein Simulationsframe. Gibt die in diesem Frame entstandenen Events zurueck."""
        produced: list[Event] = []

        self._face_each_other()
        self._advance(self.a, input_a, produced)
        self._advance(self.b, input_b, produced)
        self._separate()
        self._resolve_hits(self.a, self.b, produced)
        self._resolve_hits(self.b, self.a, produced)

        self.frame += 1
        self.events.extend(produced)
        return produced

    def run(self, log: list[tuple[int, int]]) -> list[Event]:
        for ia, ib in log:
            self.step(ia, ib)
        return self.events

    # ------------------------------------------------------------- Interna

    def _face_each_other(self) -> None:
        # Nur ausserhalb einer laufenden Aktion drehen: sonst wuerde ein Move mitten
        # in der Aktivphase seine Hitbox auf die andere Seite klappen.
        if self.a.state in (State.IDLE, State.WALK):
            self.a.facing = 1 if self.b.x >= self.a.x else -1
        if self.b.state in (State.IDLE, State.WALK):
            self.b.facing = 1 if self.a.x >= self.b.x else -1

    def _advance(self, f: Fighter, inp: int, out: list[Event]) -> None:
        if not f.alive:
            return

        # Blocken gilt nur ausserhalb einer eigenen Aktion: wer selbst schlaegt, deckt
        # nicht. Das Flag wird jeden Frame neu gesetzt, damit es nicht haengen bleibt.
        f.blocking = bool(inp & IN_BLOCK) and f.state not in (State.ATTACK, State.HITSTUN)

        if f.stun > 0:
            f.stun -= 1
            if f.stun == 0:
                f.state = State.IDLE
                f.move_tag = None
                f.move_frame = 0
            return

        if f.state == State.ATTACK:
            self._advance_attack(f, inp, out)
            return

        if inp & IN_ATTACK:
            self._start_move(f, "attack", out)
            return

        if f.blocking:
            f.state = State.IDLE
            return

        dx = 0
        if inp & IN_LEFT:
            dx -= self.rules.walk_speed
        if inp & IN_RIGHT:
            dx += self.rules.walk_speed
        f.x = _clamp(f.x + dx, self.rules.stage_min, self.rules.stage_max)
        f.state = State.WALK if dx else State.IDLE

    def _advance_attack(self, f: Fighter, inp: int, out: list[Event]) -> None:
        doc = f.moves[f.move_tag]  # type: ignore[index]
        frame_data = doc["frames"][f.move_frame]

        mv = frame_data.get("move")
        if mv:
            f.x = _clamp(f.x + mv[0] * f.facing, self.rules.stage_min, self.rules.stage_max)

        # Cancel: nur in einem Frame, der das Ziel-Tag ausdruecklich freigibt.
        if (inp & IN_ATTACK) and "attack" in frame_data.get("cancel", []):
            self._start_move(f, "attack", out)
            return

        f.move_frame += 1
        if f.move_frame >= len(doc["frames"]):
            out.append(Event(self.frame, "move_end", f.name))
            f.state = State.IDLE
            f.move_tag = None
            f.move_frame = 0
            f.hit_ids.clear()

    def _start_move(self, f: Fighter, tag: str, out: list[Event]) -> None:
        if tag not in f.moves:
            return
        f.state = State.ATTACK
        f.move_tag = tag
        f.move_frame = 0
        f.hit_ids.clear()
        out.append(Event(self.frame, "move_start", f.name))

    def _separate(self) -> None:
        """Haelt die Kaempfer auseinander. Symmetrisch, damit die Reihenfolge egal ist."""
        gap = self.b.x - self.a.x
        dist = abs(gap)
        if dist >= self.rules.push_apart:
            return
        need = self.rules.push_apart - dist
        # Ganzzahlig und symmetrisch aufteilen; der Rest geht an den linken Kaempfer,
        # damit das Ergebnis nicht von der Auswertungsreihenfolge abhaengt.
        half = need // 2
        rest = need - half
        sign = 1 if gap >= 0 else -1
        self.a.x = _clamp(self.a.x - rest * sign, self.rules.stage_min, self.rules.stage_max)
        self.b.x = _clamp(self.b.x + half * sign, self.rules.stage_min, self.rules.stage_max)

    def _resolve_hits(self, attacker: Fighter, defender: Fighter, out: list[Event]) -> None:
        if not attacker.alive or not defender.alive:
            return
        af = attacker.current_frame_data()
        if not af or not af.get("hit"):
            return
        df = defender.current_frame_data()
        hurt = df.get("hurt") if df else None
        if not hurt:
            hurt = _default_hurt()

        doc = attacker.moves[attacker.move_tag]  # type: ignore[index]

        for i, hit in enumerate(af["hit"]):
            key = hit.get("id") or f"{attacker.move_tag}:{attacker.move_frame}:{i}"
            if key in attacker.hit_ids:
                continue
            world_hit = _to_world(hit, attacker.x, attacker.facing)

            for hb in hurt:
                world_hurt = _to_world(hb, defender.x, defender.facing)
                if not _overlaps(world_hit, world_hurt):
                    continue

                attacker.hit_ids.add(key)
                blocking = defender.blocking
                impact = doc["on_block"] if blocking else doc["on_hit"]

                if blocking:
                    defender.state = State.BLOCKSTUN
                    defender.stun = impact["blockstun"]
                    out.append(Event(self.frame, "block", attacker.name, defender.name))
                else:
                    defender.health = max(0, defender.health - impact["damage"])
                    defender.state = State.HITSTUN
                    defender.stun = impact["hitstun"]
                    defender.move_tag = None
                    defender.move_frame = 0
                    out.append(
                        Event(self.frame, "hit", attacker.name, defender.name, impact["damage"])
                    )
                    if defender.health == 0:
                        out.append(Event(self.frame, "ko", attacker.name, defender.name))

                defender.x = _clamp(
                    defender.x + impact["pushback"][0] * attacker.facing,
                    self.rules.stage_min,
                    self.rules.stage_max,
                )
                break

    # ------------------------------------------------------------ Ausgabe

    def snapshot(self) -> dict:
        return {"frame": self.frame, "a": self.a.snapshot(), "b": self.b.snapshot()}


def _to_world(box: dict, x: int, facing: int) -> tuple[int, int, int, int, int, int]:
    """Baked-AABB -> Weltraum. Alles ganzzahlig.

    Bei ``facing == -1`` wird an der eigenen Ursprungsachse gespiegelt: ``min.x' = -max.x``.
    Nur ``x -> -x`` auf beiden Werten wuerde ``min`` und ``max`` vertauschen und die Box
    um ihre Breite verschieben.
    """
    lo, hi = box["min"], box["max"]
    if facing >= 0:
        x0, x1 = lo[0], hi[0]
    else:
        x0, x1 = -hi[0], -lo[0]
    return (x + x0, lo[1], lo[2], x + x1, hi[1], hi[2])


def _overlaps(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    return (
        a[0] < b[3] and b[0] < a[3]
        and a[1] < b[4] and b[1] < a[4]
        and a[2] < b[5] and b[2] < a[5]
    )


def _default_hurt() -> list[dict]:
    """Hurtbox fuer einen Kaempfer ausserhalb einer Aktion.

    Ein Kaempfer ohne aktiven Clip haette sonst gar keine Trefferflaeche und waere
    unverwundbar -- ein stiller Fehler, der erst im Spiel auffaellt.
    """
    return [{"min": [-45, 0, -45], "max": [45, 435, 45]}]


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v
