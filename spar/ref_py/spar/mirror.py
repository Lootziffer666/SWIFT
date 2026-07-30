"""Mirror-Bake: Spiegelung an der YZ-Ebene als eigener Schritt.

Bewusst **nicht** implizit im Renderer oder im FK. Ein ``facingSign``-Faktor, der beim
Loesen der Kette Winkel negiert, ist als MVP verbreitet und falsch:

* Bei asymmetrisch parametrisierten Rest-Posen entstehen vertauschte Glieder.
* Achsenparallele Boxen landen um ihre eigene Breite verschoben, weil ``x -> -x`` auf
  ``min`` und ``max`` einzeln angewandt die beiden vertauscht.

Korrekt ist: Rotationskanaele ueber die Symmetrie-Tabelle des Rigs tauschen,
Quaternionen spiegeln, Boxen ueber ``min.x' = -max.x`` spiegeln.
"""

from __future__ import annotations

from dataclasses import replace

from . import quat
from .combat import Box, CombatData, CombatFrame, Impact
from .glb import Clip
from .rig import Rig


def mirror_clip(rig: Rig, clip: Clip) -> Clip:
    """Spiegelt Rotationskanaele und visuelle Root-Motion."""
    rotations: dict[str, list[quat.Quat]] = {}
    for name in rig.names:
        # Der Kanal des Symmetriepartners wandert auf diesen Bone.
        track = clip.rotations.get(rig.mirror_of(name))
        if track is None:
            continue
        rotations[name] = [quat.mirror_x(q) for q in track]

    return Clip(
        name=f"{clip.name}_mirrored",
        fps=clip.fps,
        frame_count=clip.frame_count,
        rig_id=clip.rig_id,
        rotations=rotations,
        root_translation=[(-t[0], t[1], t[2]) for t in clip.root_translation],
    )


def mirror_box(rig: Rig, box: Box) -> Box:
    """Spiegelt eine node-lokale Box.

    ``min.x' = -max.x`` und ``max.x' = -min.x``. Nur ``x -> -x`` auf beiden Werten waere
    falsch: die Box laege dann um ihre eigene Breite daneben und ``min > max``.
    """
    return Box(
        node=rig.mirror_of(box.node),
        min=(-box.max[0], box.min[1], box.min[2]),
        max=(-box.min[0], box.max[1], box.max[2]),
        id=box.id,
    )


def mirror_combat(rig: Rig, data: CombatData) -> CombatData:
    """Spiegelt Boxen und richtungsabhaengige Groessen der Kampfdaten."""
    frames = [
        CombatFrame(
            frame=f.frame,
            flags=list(f.flags),
            hit=[mirror_box(rig, b) for b in f.hit],
            hurt=[mirror_box(rig, b) for b in f.hurt],
            cancel=list(f.cancel),
            move=(-f.move[0], f.move[1], f.move[2]),
        )
        for f in data.frames
    ]
    return replace(
        data,
        frames=frames,
        on_hit=_mirror_impact(data.on_hit),
        on_block=_mirror_impact(data.on_block),
    )


def _mirror_impact(i: Impact) -> Impact:
    return Impact(
        damage=i.damage,
        hitstun=i.hitstun,
        blockstun=i.blockstun,
        pushback=(-i.pushback[0], i.pushback[1], i.pushback[2]),
    )
