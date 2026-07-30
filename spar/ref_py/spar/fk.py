"""Forward Kinematics in 3D.

Gleitkomma, und das ist zulaessig: FK laeuft zur Bake-Zeit und zum Rendern, nie im
Gameplay-Pfad. Siehe ``spec/determinism.md``.

Generisch ueber die Rig-Hierarchie -- der Code kennt keine Arme und keine Beine, nur
Eltern und Kinder. Ein Sechsbeiner laeuft hier ohne Aenderung durch.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import quat
from .glb import Clip
from .rig import Rig


@dataclass(frozen=True)
class BonePose:
    """Welttransform eines Bones in einem Frame."""

    position: quat.Vec3
    """Weltposition des Bone-Ursprungs (Gelenk)."""
    rotation: quat.Quat
    """Weltrotation."""

    def local_to_world(self, p: quat.Vec3) -> quat.Vec3:
        return quat.add(self.position, quat.apply(self.rotation, p))


def solve(
    rig: Rig, clip: Clip, frame: int, include_root_translation: bool = False
) -> dict[str, BonePose]:
    """Loest alle Bone-Welttransforms fuer einen Frame.

    Ein einzelner Vorwaertsdurchlauf genuegt, weil ``Rig`` seine Bones topologisch
    sortiert haelt -- Eltern stehen immer vor Kindern.

    ``include_root_translation`` steuert die visuelle Root-Motion aus dem glTF. Beim
    **Bake ist sie ausgeschaltet** (Root im Ursprung): die Kollisionsposition kommt
    ausschliesslich aus der Gameplay-Root-Motion (``move`` im Combat-Sidecar), die der
    Simulator aufaddiert. Waeren beide aktiv, wuerde die Bewegung doppelt zaehlen --
    genau der Klassiker, bei dem die Figur optisch vorlaeuft, waehrend ihre Hitbox
    stehen bleibt, oder umgekehrt.
    """
    out: dict[str, BonePose] = {}

    for bone in rig:
        local_rot = clip.rotation_at(bone.name, frame)

        if bone.parent is None:
            translation = bone.offset
            if include_root_translation:
                translation = quat.add(translation, clip.root_at(frame))
            out[bone.name] = BonePose(translation, quat.canonical(local_rot))
            continue

        parent = out[bone.parent]
        out[bone.name] = BonePose(
            position=quat.add(parent.position, quat.apply(parent.rotation, bone.offset)),
            rotation=quat.canonical(quat.mul(parent.rotation, local_rot)),
        )

    return out


def segments(rig: Rig, pose: dict[str, BonePose]) -> list[tuple[str, quat.Vec3, quat.Vec3]]:
    """Knochensegmente als (Name, Anfang, Ende) -- fuer Renderer und Diagnose."""
    return [
        (b.name, pose[b.parent].position, pose[b.name].position)
        for b in rig
        if b.parent is not None
    ]


def bone_length(rig: Rig, pose: dict[str, BonePose], bone: str) -> float:
    """Gemessene Weltlaenge eines Segments.

    Muss ueber alle Frames konstant und gleich ``Bone.rest_length`` sein. Weicht sie ab,
    ist entweder ein scale-Kanal durchgerutscht oder das FK ist falsch -- in beiden
    Faellen ist die Kernaussage des Formats verletzt, dass Verkuerzung nur Rotation
    sein kann. ``cue.check_bone_lengths`` prueft das ueber einen ganzen Clip.
    """
    b = rig.by_name[bone]
    if b.parent is None:
        return 0.0
    return quat.length(quat.sub(pose[bone].position, pose[b.parent].position))


def center_of_mass(rig: Rig, pose: dict[str, BonePose]) -> quat.Vec3:
    """Massenschwerpunkt aus der Massenverteilung des Rigs.

    Grundlage der Balance-Pruefung. Zu *pruefen*, ob der Schwerpunkt ueber der
    Stuetzflaeche liegt, ist reine Geometrie und billig. Balance zu *erzeugen* ist
    Physik und ein eigenes Vorhaben -- die beiden nicht zu verwechseln ist der Grund,
    warum hier nur der Schwerpunkt steht.
    """
    if not rig.mass:
        pts = [pose[b.name].position for b in rig]
        n = float(len(pts)) or 1.0
        return (
            sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n,
        )

    total = sum(rig.mass.values()) or 1.0
    acc = (0.0, 0.0, 0.0)
    for name, w in rig.mass.items():
        acc = quat.add(acc, quat.scale(pose[name].position, w))
    return quat.scale(acc, 1.0 / total)
