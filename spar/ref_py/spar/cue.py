"""L6 -- CUE-Pruefungen: stimmt das?

Diese Schicht kommt in der Baureihenfolge bewusst vor Ausdruck und Intent. Pruefungen
sind das, was die unteren Schichten falsifizierbar macht: ohne sie ist "die Bewegung
sieht besser aus" eine Geschmacksfrage, mit ihnen ist Fussrutschen eine Zahl. Jede
Schicht, die vor ihrer Pruefung gebaut wird, sammelt stillschweigend Fehler ein.

Eine nuechterne Trennung, die in Architekturgespraechen gern verschwimmt: Balance zu
*pruefen* ist billig -- Schwerpunkt ueber dem Stuetzpolygon, reine Geometrie. Balance zu
*erzeugen* ist Physik oder ein gelerntes Modell und ein eigenes Vorhaben. Hier steht nur
die Pruefung.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import fk, quat
from .glb import Clip
from .rig import Rig


@dataclass(frozen=True)
class Finding:
    check: str
    frame: int | None
    subject: str
    detail: str
    severity: str = "error"  # "error" | "warning"

    def __str__(self) -> str:
        where = f"Frame {self.frame}" if self.frame is not None else "Clip"
        return f"[{self.severity}] {self.check}: {where}, {self.subject} -- {self.detail}"


# ------------------------------------------------------------ Knochenlaengen


def check_bone_lengths(rig: Rig, clip: Clip, tolerance: float = 1e-4) -> list[Finding]:
    """Knochenlaengen muessen ueber alle Frames konstant und gleich der Rest-Laenge sein.

    Das ist die Kernaussage des Formats: perspektivische Verkuerzung entsteht nur durch
    Rotation. Schlaegt diese Pruefung an, ist entweder ein ``scale``-Kanal
    durchgerutscht oder das FK ist falsch.
    """
    out: list[Finding] = []
    for frame in range(clip.frame_count):
        pose = fk.solve(rig, clip, frame)
        for bone in rig:
            if bone.parent is None:
                continue
            measured = fk.bone_length(rig, pose, bone.name)
            drift = abs(measured - bone.rest_length)
            if drift > tolerance:
                out.append(
                    Finding(
                        "bone_length",
                        frame,
                        bone.name,
                        f"gemessen {measured:.5f} m, erwartet {bone.rest_length:.5f} m "
                        f"(Abweichung {drift:.2e})",
                    )
                )
    return out


# -------------------------------------------------------------- Gelenkgrenzen


def swing_twist(q: quat.Quat, axis: quat.Vec3) -> tuple[float, float]:
    """Zerlegt eine Rotation in Schwenk- und Drehwinkel um ``axis``, in Grad.

    Standard-Swing-Twist-Zerlegung: Der Anteil des Quaternion-Vektors entlang der Achse
    ergibt den Twist, der Rest ist Swing.
    """
    ax, ay, az = axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        return (0.0, 0.0)
    ax, ay, az = ax / n, ay / n, az / n

    qx, qy, qz, qw = quat.normalize(q)
    dot = qx * ax + qy * ay + qz * az
    twist = quat.normalize((ax * dot, ay * dot, az * dot, qw))
    twist_angle = 2.0 * math.atan2(
        math.copysign(math.sqrt(sum(c * c for c in twist[:3])), dot), twist[3]
    )

    swing = quat.mul((qx, qy, qz, qw), quat.conjugate(twist))
    swing_angle = 2.0 * math.acos(max(-1.0, min(1.0, abs(swing[3]))))

    return (math.degrees(swing_angle), math.degrees(_wrap_pi(twist_angle)))


def _wrap_pi(a: float) -> float:
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def _twist_axis(rig: Rig, bone_name: str) -> quat.Vec3:
    """Achse, um die ein Gelenk 'dreht' statt 'schwenkt'.

    Standardmaessig die Richtung zum ersten Kind -- das ist die Achse entlang des
    Segments. Fuer Blattknoten faellt sie auf +Y zurueck.
    """
    kids = rig.children_of(bone_name)
    if kids:
        off = rig.by_name[kids[0]].offset
        if quat.length(off) > 1e-9:
            return off
    return (0.0, 1.0, 0.0)


def check_joint_limits(rig: Rig, clip: Clip, tolerance: float = 0.5) -> list[Finding]:
    """Prueft lokale Rotationen gegen die Gelenkgrenzen des Rigs.

    Dieselbe Funktion, die der Holzpuppen-Editor braucht, um Gliedmassen nur so
    verschieben zu lassen, wie das Gelenk es zulaesst.
    """
    out: list[Finding] = []
    for frame in range(clip.frame_count):
        for bone in rig:
            j = bone.joint
            if j.type == "fixed":
                continue
            q = clip.rotation_at(bone.name, frame)

            if j.type == "hinge":
                assert j.axis is not None and j.range is not None
                swing, twist = swing_twist(q, j.axis)
                if swing > tolerance:
                    out.append(
                        Finding(
                            "joint_limit",
                            frame,
                            bone.name,
                            f"Scharnier ausserhalb seiner Achse: {swing:.1f} Grad Schwenk",
                        )
                    )
                lo, hi = j.range
                if not (lo - tolerance <= twist <= hi + tolerance):
                    out.append(
                        Finding(
                            "joint_limit",
                            frame,
                            bone.name,
                            f"Scharnierwinkel {twist:.1f} Grad ausserhalb [{lo}, {hi}]",
                        )
                    )
                continue

            axis = _twist_axis(rig, bone.name)
            swing, twist = swing_twist(q, axis)
            if j.swing is not None and swing > j.swing + tolerance:
                out.append(
                    Finding(
                        "joint_limit",
                        frame,
                        bone.name,
                        f"Schwenk {swing:.1f} Grad ueber Grenze {j.swing}",
                    )
                )
            if j.twist is not None:
                lo, hi = j.twist
                if not (lo - tolerance <= twist <= hi + tolerance):
                    out.append(
                        Finding(
                            "joint_limit",
                            frame,
                            bone.name,
                            f"Drehung {twist:.1f} Grad ausserhalb [{lo}, {hi}]",
                        )
                    )
    return out


# ------------------------------------------------------------ Fussrutschen


def check_foot_slide(
    rig: Rig, clip: Clip, ground_y: float = 0.0, threshold: float = 0.005
) -> list[Finding]:
    """Kontaktpunkte duerfen sich nicht bewegen, solange sie am Boden sind.

    Fussrutschen ist der haeufigste Grund, warum uebertragene Bewegung "clunky" wirkt --
    und im Gegensatz zum Gesamteindruck ist es messbar. Genau deshalb gehoert es hierher
    und nicht in eine Geschmacksdiskussion.
    """
    out: list[Finding] = []
    contacts = rig.contacts_of_kind("ground")
    if not contacts:
        return out

    previous: dict[str, quat.Vec3] = {}
    for frame in range(clip.frame_count):
        pose = fk.solve(rig, clip, frame, include_root_translation=True)
        for c in contacts:
            world = pose[c.node].local_to_world(c.point)
            grounded = world[1] <= ground_y + threshold
            if grounded and c.name in previous:
                moved = quat.length(quat.sub(world, previous[c.name]))
                if moved > threshold:
                    out.append(
                        Finding(
                            "foot_slide",
                            frame,
                            c.name,
                            f"Kontakt am Boden um {moved * 1000:.1f} mm verschoben",
                            severity="warning",
                        )
                    )
            previous[c.name] = world if grounded else previous.pop(c.name, world)
            if not grounded:
                previous.pop(c.name, None)
    return out


# ----------------------------------------------------------------- Balance


def check_balance(rig: Rig, clip: Clip, ground_y: float = 0.0, margin: float = 0.02) -> list[Finding]:
    """Schwerpunkt muss ueber der Stuetzflaeche liegen.

    Reine Geometrie: Projektion des Massenschwerpunkts auf die XZ-Ebene, verglichen mit
    der Huelle der Bodenkontakte. Das *prueft* Balance -- es erzeugt sie nicht.
    """
    out: list[Finding] = []
    contacts = rig.contacts_of_kind("ground")
    if not contacts or not rig.mass:
        return out

    for frame in range(clip.frame_count):
        pose = fk.solve(rig, clip, frame, include_root_translation=True)
        com = fk.center_of_mass(rig, pose)

        support = [
            pose[c.node].local_to_world(c.point)
            for c in contacts
            if pose[c.node].local_to_world(c.point)[1] <= ground_y + 0.01
        ]
        if not support:
            continue  # in der Luft -- Balance ist dort keine Aussage

        xs = [p[0] for p in support]
        zs = [p[2] for p in support]
        inside = (
            min(xs) - margin <= com[0] <= max(xs) + margin
            and min(zs) - margin <= com[2] <= max(zs) + margin
        )
        if not inside:
            out.append(
                Finding(
                    "balance",
                    frame,
                    "center_of_mass",
                    f"Schwerpunkt ({com[0]:.3f}, {com[2]:.3f}) ausserhalb der Stuetzflaeche "
                    f"x[{min(xs):.3f}, {max(xs):.3f}] z[{min(zs):.3f}, {max(zs):.3f}]",
                    severity="warning",
                )
            )
    return out


# -------------------------------------------------------------------- alle


def run_all(rig: Rig, clip: Clip) -> list[Finding]:
    return (
        check_bone_lengths(rig, clip)
        + check_joint_limits(rig, clip)
        + check_foot_slide(rig, clip)
        + check_balance(rig, clip)
    )


def summarize(findings: list[Finding], limit: int = 12) -> str:
    if not findings:
        return "CUE: keine Beanstandungen"
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    lines = [f"CUE: {len(errors)} Fehler, {len(warnings)} Warnungen"]
    by_check: dict[str, int] = {}
    for f in findings:
        by_check[f.check] = by_check.get(f.check, 0) + 1
    for check, n in sorted(by_check.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {check}: {n}")
    lines.append("")
    for f in findings[:limit]:
        lines.append(f"  {f}")
    if len(findings) > limit:
        lines.append(f"  ... und {len(findings) - limit} weitere")
    return "\n".join(lines)
