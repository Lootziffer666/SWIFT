"""Gold-Clip: ein von Hand autorisierter Jab.

Bewusst von Hand und bewusst klein. M2 soll das *Format* pruefen, nicht den Importer --
solange der Gold-Clip aus einer Extraktionspipeline kaeme, wuesste man bei einem Fehler
nie, welche der beiden Seiten ihn verursacht hat.

3 Startup-Frames, 2 Active, 2 Recovery. Rechte Gerade, linker Arm bleibt in Deckung.
"""

from __future__ import annotations

import math
from pathlib import Path

from . import bake as bake_mod
from . import fk, quat
from .combat import Box, CombatData, CombatFrame, Impact
from .glb import Clip, write_clip
from .rig import Rig

FPS = 60


def _pose(
    arm_r: tuple[float, float, float],
    fore_r: float,
    arm_l: tuple[float, float, float] = (76.0, -22.0, 0.0),
    fore_l: float = 105.0,
    spine: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, quat.Quat]:
    """Eine Pose aus wenigen Winkeln. Angaben in Grad als (Z, Y, X).

    Ellbogen sind Scharniere um Z -- deshalb genuegt dort ein einziger Wert, und jeder
    andere Wert waere laut Rig ohnehin unzulaessig.

    Zum Vorzeichen: Die Arme liegen in Ruhe entlang +X (rechts) und -X (links). Eine
    Drehung um Z bildet (1,0) auf (cos, sin) ab, aber (-1,0) auf (-cos, -sin) -- der
    linke Arm braucht fuer dieselbe Bewegung nach unten also das *entgegengesetzte*
    Vorzeichen. Genau dieser Fallstrick ist der Grund, warum Spiegelung im Format ein
    eigener Bake-Schritt ist und kein Vorzeichenfaktor im FK.
    """
    return {
        "Spine": quat.from_euler_zyx(*spine),
        "Chest": quat.from_euler_zyx(spine[0] * 0.5, spine[1] * 0.6, 0.0),
        "Arm.R": quat.from_euler_zyx(*arm_r),
        "Forearm.R": quat.from_euler_zyx(fore_r, 0.0, 0.0),
        "Arm.L": quat.from_euler_zyx(*arm_l),
        "Forearm.L": quat.from_euler_zyx(fore_l, 0.0, 0.0),
        # Leichter Kampfstand: Beine bleiben ueber die ganze Sequenz ruhig, damit die
        # Fussrutsch-Pruefung ein sauberes Signal hat.
        "Leg.L": quat.from_euler_zyx(6.0, 0.0, 0.0),
        "Leg.R": quat.from_euler_zyx(-6.0, 0.0, 0.0),
        "Shin.L": quat.from_euler_zyx(0.0, 0.0, -8.0),
        "Shin.R": quat.from_euler_zyx(0.0, 0.0, -8.0),
        "Foot.L": quat.from_euler_zyx(0.0, 0.0, 8.0),
        "Foot.R": quat.from_euler_zyx(0.0, 0.0, 8.0),
    }


# (Arm.R als Z/Y/X, Forearm.R-Scharnier, Spine-Drehung)
_KEYS = [
    ((-78.0, 18.0, 0.0), -110.0, (0.0, 10.0, 0.0)),  # 0 Deckung
    ((-80.0, 10.0, 0.0), -118.0, (0.0, 15.0, 0.0)),  # 1 Ausholen
    ((-74.0, 38.0, 0.0), -88.0, (0.0, 5.0, 0.0)),    # 2 Start
    ((-62.0, 76.0, 0.0), -26.0, (0.0, -14.0, 0.0)),  # 3 aktiv
    ((-58.0, 88.0, 0.0), -8.0, (0.0, -20.0, 0.0)),   # 4 aktiv, volle Streckung
    ((-70.0, 50.0, 0.0), -62.0, (0.0, -5.0, 0.0)),   # 5 Recovery
    ((-78.0, 18.0, 0.0), -110.0, (0.0, 10.0, 0.0)),  # 6 zurueck in Deckung
]


def build_clip(rig: Rig) -> Clip:
    rotations: dict[str, list[quat.Quat]] = {}
    for arm_r, fore_r, spine in _KEYS:
        for bone, q in _pose(arm_r, fore_r, spine=spine).items():
            rotations.setdefault(bone, []).append(q)

    clip = Clip(
        name="jab",
        fps=FPS,
        frame_count=len(_KEYS),
        rig_id=rig.id,
        rotations=rotations,
    )
    # Wurzelhoehe so setzen, dass die Bodenkontakte auf y = 0 liegen. Berechnet statt
    # geraten -- sonst haengt die Figur in der Luft und die Balance-Pruefung schweigt.
    clip.root_translation = [(0.0, _ground_offset(rig, clip), 0.0)] * clip.frame_count
    return clip


def _ground_offset(rig: Rig, clip: Clip) -> float:
    pose = fk.solve(rig, clip, 0, include_root_translation=False)
    ys = [
        pose[c.node].local_to_world(c.point)[1]
        for c in rig.contacts_of_kind("ground")
    ]
    return -min(ys) if ys else 0.0


def build_combat(rig: Rig) -> CombatData:
    """Kampfdaten zum Jab.

    Hurtboxen liegen auf Chest und Hips, die Hitbox auf Hand.R -- und zwar nur in den
    Frames 3 und 4. Startup/Active/Recovery werden daraus abgeleitet
    (``combat.derive_phases``) statt gespeichert; so bleiben spaeter auch Moves mit
    mehreren Trefferphasen darstellbar.
    """
    hurt = [
        Box("Chest", (-0.11, -0.06, -0.11), (0.11, 0.22, 0.11)),
        Box("Hips", (-0.11, -0.06, -0.10), (0.11, 0.16, 0.10)),
    ]
    fist = Box("Hand.R", (-0.05, -0.05, -0.05), (0.09, 0.05, 0.05), id="jab_fist")

    frames = []
    for i in range(len(_KEYS)):
        frames.append(
            CombatFrame(
                frame=i,
                flags=["grounded"],
                hit=[fist] if i in (3, 4) else [],
                hurt=list(hurt),
                cancel=["attack"] if i in (4, 5) else [],
                move=(0.06, 0.0, 0.0) if i in (2, 3) else (0.0, 0.0, 0.0),
            )
        )

    return CombatData(
        clip="jab.glb",
        animation="jab",
        fps=FPS,
        frame_count=len(_KEYS),
        frames=frames,
        tags=["attack", "punch", "standing", "light"],
        on_hit=Impact(damage=4, hitstun=10, pushback=(0.18, 0.0, 0.0)),
        on_block=Impact(blockstun=7, pushback=(0.12, 0.0, 0.0)),
    )


def build(out_dir: str | Path, rig: Rig) -> dict[str, Path]:
    """Schreibt Clip, Kampfdaten und Bake nach ``out_dir``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    clip = build_clip(rig)
    data = build_combat(rig)

    glb_path = write_clip(out / "jab.glb", clip, rig)
    combat_path = data.save(out / "jab.combat.json")
    baked = bake_mod.bake(
        rig, clip, data, clip_name="jab.glb", combat_name="jab.combat.json"
    )
    baked_path = bake_mod.save(baked, out / "jab.baked.json")

    return {"clip": glb_path, "combat": combat_path, "baked": baked_path}
