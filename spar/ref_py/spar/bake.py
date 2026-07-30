"""Bake: node-relative Boxen -> Weltraum-AABBs als Fixed-Point-Integer.

Das ist der Schritt, der Engine-Agnostik praktisch macht. Fighter-Clips sind
vorautorisiert -- die Pose zu Frame *n* steht fest, bevor das Spiel startet. Also wird die
Welt-AABB jeder Box hier **einmal** ausgerechnet und ganzzahlig abgelegt.

Die Runtime schlaegt sie danach nur noch nach, verschiebt sie um die ganzzahlige
Kaempferposition und testet ganzzahlig auf Ueberlappung: kein ``sin``, kein Quaternion,
kein plattformabhaengiges Rundungsverhalten im Gameplay-Pfad. Deshalb koennen zwei
Implementierungen in verschiedenen Sprachen bit-identisch simulieren.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import fk, fixed
from .combat import Box, CombatData, Impact
from .glb import Clip
from .rig import Rig


def bake(
    rig: Rig,
    clip: Clip,
    data: CombatData,
    mirrored: bool = False,
    clip_name: str | None = None,
    combat_name: str | None = None,
) -> dict:
    """Erzeugt ein ``fcd-baked/1``-Dokument."""
    frames_out = []

    for cf in data.frames:
        # Root im Ursprung: die Kollisionsposition kommt aus der Gameplay-Root-Motion,
        # die der Simulator aufaddiert, nicht aus der visuellen Root-Motion des Clips.
        pose = fk.solve(rig, clip, cf.frame, include_root_translation=False)

        entry: dict = {
            "frame": cf.frame,
            "hit": [_bake_box(b, pose) for b in cf.hit],
            "hurt": [_bake_box(b, pose) for b in cf.hurt],
        }
        if cf.flags:
            entry["flags"] = list(cf.flags)
        if cf.cancel:
            entry["cancel"] = list(cf.cancel)
        if any(cf.move):
            entry["move"] = [fixed.to_fixed(c) for c in cf.move]
        frames_out.append(entry)

    return {
        "schema": "fcd-baked/1",
        "unit_scale": fixed.UNIT_SCALE,
        "fps": data.fps,
        "frame_count": data.frame_count,
        "source": {
            "clip": clip_name or data.clip,
            "combat": combat_name or "",
            "animation": data.animation,
            "rig": rig.id,
            "mirrored": mirrored,
        },
        "tags": list(data.tags),
        "frames": frames_out,
        "on_hit": _bake_impact(data.on_hit),
        "on_block": _bake_impact(data.on_block),
    }


def _bake_box(box: Box, pose: dict[str, fk.BonePose]) -> dict:
    """Transformiert eine node-lokale Box in eine Weltraum-AABB.

    Die Box rotiert mit dem Bone, das Ergebnis ist aber achsenparallel. Deshalb werden
    alle acht Ecken transformiert und darueber die Huelle gebildet -- nicht nur min und
    max, was bei rotierten Boxen eine zu kleine Huelle ergaebe.
    """
    if box.node not in pose:
        raise KeyError(f"Box referenziert unbekannten Node {box.node!r}")
    bone = pose[box.node]

    xs, ys, zs = [], [], []
    for cx in (box.min[0], box.max[0]):
        for cy in (box.min[1], box.max[1]):
            for cz in (box.min[2], box.max[2]):
                wx, wy, wz = bone.local_to_world((cx, cy, cz))
                xs.append(wx)
                ys.append(wy)
                zs.append(wz)

    # Konservativ: min abwaerts, max aufwaerts. Eine gebakene Box ist damit nie kleiner
    # als die exakte, und Rundung kann keinen Treffer verschlucken.
    out: dict = {
        "min": [fixed.floor_fixed(min(xs)), fixed.floor_fixed(min(ys)), fixed.floor_fixed(min(zs))],
        "max": [fixed.ceil_fixed(max(xs)), fixed.ceil_fixed(max(ys)), fixed.ceil_fixed(max(zs))],
        "node": box.node,  # nur Diagnose; die Runtime ignoriert das Feld
    }
    if box.id:
        out["id"] = box.id
    return out


def _bake_impact(i: Impact) -> dict:
    return {
        "damage": i.damage,
        "hitstun": i.hitstun,
        "blockstun": i.blockstun,
        "pushback": [fixed.to_fixed(c) for c in i.pushback],
    }


def save(doc: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return path


def load(path: str | Path) -> dict:
    doc = json.loads(Path(path).read_text())
    if doc.get("schema") != "fcd-baked/1":
        raise ValueError(f"Erwartet schema 'fcd-baked/1', gefunden {doc.get('schema')!r}")
    if doc.get("unit_scale") != fixed.UNIT_SCALE:
        raise ValueError(
            f"unit_scale {doc.get('unit_scale')} passt nicht zu UNIT_SCALE={fixed.UNIT_SCALE}"
        )
    return doc
