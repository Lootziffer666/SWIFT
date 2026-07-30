"""Laden und Auswerten von Kampfdaten (``fcd/1`` Autoren-Format, ``fcd-baked/1`` Runtime)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

Vec3f = tuple[float, float, float]


@dataclass(frozen=True)
class Box:
    """Hit- oder Hurtbox im lokalen Raum eines glTF-Nodes."""

    node: str
    min: Vec3f
    max: Vec3f
    id: str | None = None


@dataclass
class Impact:
    damage: int = 0
    hitstun: int = 0
    blockstun: int = 0
    pushback: Vec3f = (0.0, 0.0, 0.0)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Impact":
        d = d or {}
        pb = d.get("pushback") or [0.0, 0.0, 0.0]
        return cls(
            damage=int(d.get("damage", 0)),
            hitstun=int(d.get("hitstun", 0)),
            blockstun=int(d.get("blockstun", 0)),
            pushback=(float(pb[0]), float(pb[1]), float(pb[2])),
        )


@dataclass
class CombatFrame:
    frame: int
    flags: list[str] = field(default_factory=list)
    hit: list[Box] = field(default_factory=list)
    hurt: list[Box] = field(default_factory=list)
    cancel: list[str] = field(default_factory=list)
    move: Vec3f = (0.0, 0.0, 0.0)


@dataclass
class CombatData:
    """Autoren-Format ``fcd/1``."""

    clip: str
    animation: str
    fps: int
    frame_count: int
    frames: list[CombatFrame]
    tags: list[str] = field(default_factory=list)
    on_hit: Impact = field(default_factory=Impact)
    on_block: Impact = field(default_factory=Impact)

    @classmethod
    def load(cls, path: str | Path) -> "CombatData":
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, data: dict) -> "CombatData":
        if data.get("schema") != "fcd/1":
            raise ValueError(f"Erwartet schema 'fcd/1', gefunden {data.get('schema')!r}")

        by_index = {f["frame"]: f for f in data["frames"]}
        frames = []
        for i in range(data["frame_count"]):
            raw = by_index.get(i, {})
            mv = raw.get("move") or [0.0, 0.0, 0.0]
            frames.append(
                CombatFrame(
                    frame=i,
                    flags=list(raw.get("flags", [])),
                    hit=[_box(b) for b in raw.get("hit", [])],
                    hurt=[_box(b) for b in raw.get("hurt", [])],
                    cancel=list(raw.get("cancel", [])),
                    move=(float(mv[0]), float(mv[1]), float(mv[2])),
                )
            )

        return cls(
            clip=data["clip"],
            animation=data["animation"],
            fps=int(data["fps"]),
            frame_count=int(data["frame_count"]),
            frames=frames,
            tags=list(data.get("tags", [])),
            on_hit=Impact.from_dict(data.get("on_hit")),
            on_block=Impact.from_dict(data.get("on_block")),
        )

    def to_dict(self) -> dict:
        out: dict = {
            "schema": "fcd/1",
            "clip": self.clip,
            "animation": self.animation,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "tags": self.tags,
            "frames": [],
        }
        for f in self.frames:
            entry: dict = {"frame": f.frame}
            if f.flags:
                entry["flags"] = f.flags
            if f.hit:
                entry["hit"] = [_box_dict(b) for b in f.hit]
            if f.hurt:
                entry["hurt"] = [_box_dict(b) for b in f.hurt]
            if f.cancel:
                entry["cancel"] = f.cancel
            if any(f.move):
                entry["move"] = list(f.move)
            out["frames"].append(entry)
        out["on_hit"] = _impact_dict(self.on_hit)
        out["on_block"] = _impact_dict(self.on_block)
        return out

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path


def derive_phases(data: CombatData) -> dict[str, list[int]]:
    """Leitet Startup / Active / Recovery aus der Eventspur ab.

    Bewusst eine **Ansicht**, keine gespeicherte Wahrheit. Waeren die Phasen die Quelle,
    liessen sich Moves mit mehreren Trefferphasen (Rekka, Multi-Hit) nicht abbilden --
    genau die Einschraenkung, an der bereichsbasierte Frame-Data-Modelle scheitern.

    Bei mehreren Active-Bloecken sind alle Treffer-Frames in ``active`` enthalten; die
    Luecken dazwischen erscheinen weder in ``startup`` noch in ``recovery``.
    """
    active = [f.frame for f in data.frames if f.hit]
    if not active:
        return {"startup": [], "active": [], "recovery": [f.frame for f in data.frames]}
    first, last = active[0], active[-1]
    return {
        "startup": [f.frame for f in data.frames if f.frame < first],
        "active": active,
        "recovery": [f.frame for f in data.frames if f.frame > last],
    }


def _box(d: dict) -> Box:
    return Box(
        node=d["node"],
        min=(float(d["min"][0]), float(d["min"][1]), float(d["min"][2])),
        max=(float(d["max"][0]), float(d["max"][1]), float(d["max"][2])),
        id=d.get("id"),
    )


def _box_dict(b: Box) -> dict:
    d: dict = {"node": b.node, "min": list(b.min), "max": list(b.max)}
    if b.id:
        d["id"] = b.id
    return d


def _impact_dict(i: Impact) -> dict:
    return {
        "damage": i.damage,
        "hitstun": i.hitstun,
        "blockstun": i.blockstun,
        "pushback": list(i.pushback),
    }
