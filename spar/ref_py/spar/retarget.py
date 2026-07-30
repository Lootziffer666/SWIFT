"""Retargeting, das Kontakte erhaelt statt Winkel -- Schicht L3.

Wer Gelenkwinkel eins zu eins auf einen anders proportionierten Koerper uebertraegt,
bekommt Fussrutschen und Haende, die neben der Waffe landen. Die Winkel sind naemlich
gar nicht die Aussage der Bewegung -- die Aussage ist, dass der Fuss auf dem Boden
steht und die Hand am Griff bleibt. **Kontakte sind das Invariante, Gelenkwinkel das
Verhandelbare.**

Umfang
------
Gleiche Topologie, andere Proportionen: ``biped/1`` auf einen staemmigeren Biped. Eine
Uebertragung zwischen *verschiedenen* Topologien braucht eine Gliedmassen-Zuordnung
(welches der sechs Beine entspricht welchem der zwei?) und ist ein eigenes Vorhaben.

Der Sechsbeiner laeuft hier trotzdem durch -- als Generalitaetsnachweis. Der Loeser
kennt keine Beine, nur Ketten, die er von der Kontaktstelle aus zwei Eltern aufwaerts
findet. Steht irgendwo ``Foot`` oder ``Leg`` im Code, ist er falsch.

Gleitkomma, wie FK: laeuft zur Bake-Zeit, nie im Gameplay-Pfad. Siehe
``spec/determinism.md``.

Herkunft
--------
Zwei-Knochen-IK per Kosinussatz und der Becken-Drop-vor-dem-Loesen stammen aus der
NPC-Animation von *Fallout: Ember*; der Drop ist hier von zwei Beinen auf beliebig
viele Kontakte verallgemeinert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import fk, quat
from .contact import ContactSchedule, Span
from .glb import Clip
from .rig import Rig

REACH_LIMIT = 0.995
"""Anteil der vollen Streckung, den eine Kette hoechstens ausfahren darf.

Nicht kosmetisch. Bei exakt voller Streckung liegen Huefte, Knie und Ziel auf einer
Geraden, der Kosinussatz liefert einen Kniewinkel von genau 0 und die *Beugeebene* ist
undefiniert -- das Knie kann in jede Richtung kippen. Ein Promille Reserve haelt die
Ebene bestimmt, und der Unterschied ist unsichtbar.
"""

MAX_ROOT_SHIFT = 0.42
"""Wie weit die Root hoechstens verschoben wird, relativ zur Rig-Referenzhoehe.

**Vorzeichenbehaftet.** Die Vorlage kennt nur Absenken, weil sie eine Figur auf Gelaende
stellt und Gelaende nur nach unten abweicht. Beim Retargeting gilt das nicht: laengere
Gliedmassen am Ziel heben den Koerper. Wird hier auf negative Werte geklemmt, bleibt ein
langbeiniges Ziel in der Hocke und saemtliche Kontakte reissen ab.
"""


@dataclass
class RetargetResult:
    clip: Clip
    root_shift: list[float]
    """Angewandte Root-Verschiebung je Frame, vorzeichenbehaftet -- fuer Diagnose und
    Vektoren. Negativ senkt ab, positiv hebt an."""


# ------------------------------------------------------------------ Ketten


def chain_of(rig: Rig, node: str) -> tuple[str, str, str] | None:
    """Findet die Zwei-Knochen-Kette, die ``node`` bewegt: (Wurzel, Mitte, Ende).

    Rein ueber die Hierarchie. ``Foot.L -> Shin.L -> Leg.L`` und
    ``Tibia1.L -> Femur1.L -> Coxa1.L`` liefern dasselbe Muster, weil der Code nach
    Eltern fragt und nicht nach Namen. Das ist der Hexapod-Test.
    """
    end = rig.by_name.get(node)
    if end is None or end.parent is None:
        return None
    mid = rig.by_name.get(end.parent)
    if mid is None or mid.parent is None:
        return None
    return (mid.parent, mid.name, end.name)


# ------------------------------------------------------------------ Root-Drop


def root_shift_for(
    rig: Rig,
    clip: Clip,
    schedule: ContactSchedule,
    frame: int,
    targets: dict[str, quat.Vec3],
) -> float:
    """Wie weit die Root sinken muss, damit **alle** Kontakte erreichbar bleiben.

    Das **Minimum** ueber die eingerasteten Kontakte, nicht der Mittelwert. Der
    Unterschied ist der ganze Trick: der Mittelwert laesst den tiefsten Kontakt
    unerreichbar, die Kette faehrt in die Streckung und das Bein ueberstreckt sichtbar.
    Das Minimum garantiert, dass keiner mehr reichen muss, als er kann -- die anderen
    beugen sich dann eben staerker, und Beugung ist billig.

    Zwei Anforderungen gehen ein, und die zweite ist die, die man vergisst:

    1. **Hoehe** -- der Kontakt muss auf seine Zielhoehe kommen.
    2. **Reichweite** -- die Kette muss das Ziel ueberhaupt *erreichen* koennen.

    Nur (1) zu rechnen sieht richtig aus und laesst bei kuerzeren Gliedmassen einen Rest
    stehen: das Bein faehrt in die Streckung, kommt trotzdem nicht hin, und der Fuss
    schwebt genau um die fehlende Reichweite ueber dem Boden. Weil Absenken die Huefte
    an den am Boden liegenden Zielpunkt heranbringt, loest mehr Drop genau das.

    Vektor-gepinnt durch ``contact/root-shift-is-minimum``.
    """
    pose = fk.solve(rig, clip, frame, include_root_translation=True)
    deltas = []
    for span in schedule.engaged_at(frame):
        contact = next((c for c in rig.contacts if c.name == span.site), None)
        if contact is None or span.kind not in ("planted", "sliding"):
            continue
        target = targets.get(span.site)
        if target is None:
            continue

        current = pose[contact.node].local_to_world(contact.point)
        deltas.append(target[1] - current[1])

        chain = chain_of(rig, contact.node)
        if chain is None:
            continue
        root_bone, mid_bone, end_bone = chain
        reach = (
            rig.by_name[mid_bone].rest_length + rig.by_name[end_bone].rest_length
        ) * REACH_LIMIT
        # Der Kettenanfang zielt auf den Bone-Ursprung, nicht auf den Kontaktpunkt.
        goal = quat.add(
            pose[contact.node].position, quat.sub(target, current)
        )
        v = quat.sub(goal, pose[root_bone].position)
        horizontal = v[0] * v[0] + v[2] * v[2]
        slack = reach * reach - horizontal
        if slack <= 0.0:
            continue  # auch mit beliebigem Drop nicht erreichbar
        # Beide Wurzeln erfuellen die Reichweite; die betragskleinere verschiebt am
        # wenigsten und ist damit die gesuchte.
        root = math.sqrt(slack)
        deltas.append(min(v[1] + root, v[1] - root, key=abs))

    if not deltas:
        return 0.0
    limit = MAX_ROOT_SHIFT * (rig.reference_height or 1.0)
    return min(max(combine_requirements(deltas), -limit), limit)


def combine_requirements(deltas: list[float]) -> float:
    """Wie mehrere Kontaktanforderungen zu einer Verschiebung werden: **Minimum**.

    Eigene Funktion, damit die Wahl eine benennbare Stelle hat statt ein ``min`` mitten
    in einer laengeren Rechnung -- und damit ein Test sie verbiegen und pruefen kann,
    dass die Vektoren das merken.
    """
    return min(deltas)


# ------------------------------------------------------------------ Zwei-Knochen-IK


def solve_two_bone(length_a: float, length_b: float, distance: float) -> float:
    """Kosinussatz: der **Innenwinkel am Mittelgelenk**, in Radiant.

    ``length_a`` Wurzel->Mitte, ``length_b`` Mitte->Ende, ``distance`` Wurzel->Ziel.
    Geschlossene Form -- keine Iteration, keine Konvergenz, keine
    Plattformabhaengigkeit ausser ``acos``.

    Bewusst der Innenwinkel und nicht "die Beugung gegenueber gestreckt": *gestreckt*
    setzt voraus, dass die Ruhelage der Kette gerade ist. Beim Biped stimmt das
    zufaellig -- Schienbein und Fuss zeigen beide senkrecht nach unten -- bei einem
    Insektenbein mit Femur nach aussen-oben und Tibia nach aussen-unten nicht im
    Geringsten. Der Innenwinkel ist unabhaengig von der Ruhelage; wie weit das Gelenk
    dafuer *drehen* muss, ergibt sich erst aus der Differenz zu seinem Ruhewinkel.
    """
    lo = abs(length_a - length_b) + 1e-6
    hi = (length_a + length_b) * REACH_LIMIT
    d = min(max(distance, lo), hi)

    cos_mid = (length_a * length_a + length_b * length_b - d * d) / (
        2.0 * length_a * length_b
    )
    return math.acos(min(1.0, max(-1.0, cos_mid)))


def _angle_between(a: quat.Vec3, b: quat.Vec3) -> float:
    na, nb = quat.length(a), quat.length(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    dot = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (na * nb)
    return math.acos(min(1.0, max(-1.0, dot)))


def _clamp_to_joint(rig: Rig, bone: str, rotation: quat.Quat) -> quat.Quat:
    """Haelt eine geloeste Rotation innerhalb der Gelenkgrenzen des Rigs.

    Die Grenzen stehen in der Rig-Datei (L1) und sind damit dieselbe Wahrheit, gegen
    die ``cue.check_joint_limits`` prueft. Ein Loeser, der sie ignoriert, produziert
    Posen, die die eigene CUE-Pruefung anschliessend beanstandet.
    """
    joint = rig.by_name[bone].joint
    if joint.type == "fixed":
        return quat.IDENTITY
    if joint.type == "hinge" and joint.axis is not None and joint.range is not None:
        lo, hi = joint.range
        clamped = min(max(_hinge_angle(rotation, joint.axis), lo), hi)
        return quat.canonical(quat.from_axis_angle(joint.axis, math.radians(clamped)))
    return quat.canonical(rotation)


# ------------------------------------------------------------------ Loeser


def retarget(
    source_rig: Rig,
    clip: Clip,
    schedule: ContactSchedule,
    target_rig: Rig,
) -> RetargetResult:
    """Uebertraegt ``clip`` von ``source_rig`` auf ``target_rig``.

    Reihenfolge, und sie ist nicht beliebig:

    1. Kontaktziele aus der **Quelle** merken -- das ist die zu erhaltende Aussage.
    2. Root absenken, einmal, um das Minimum ueber alle Kontakte.
    3. *Dann* je Kette die Zwei-Knochen-IK loesen.

    Wer 3 vor 2 macht, loest jede Kette gegen ein Ziel, das die Root gleich wieder
    verschiebt, und darf danach von vorn anfangen.
    """
    if source_rig.names != target_rig.names:
        raise ValueError(
            "Retargeting setzt gleiche Topologie voraus; "
            f"{source_rig.id} und {target_rig.id} haben verschiedene Bones"
        )

    out = Clip(
        name=clip.name,
        fps=clip.fps,
        frame_count=clip.frame_count,
        rig_id=target_rig.id,
        rotations={b: list(track) for b, track in clip.rotations.items()},
        root_translation=list(clip.root_translation),
    )

    shifts: list[float] = []
    for frame in range(clip.frame_count):
        # 1 -- wo die Kontakte in der Quelle liegen
        source_pose = fk.solve(source_rig, clip, frame, include_root_translation=True)
        wanted: dict[str, quat.Vec3] = {}
        for span in schedule.engaged_at(frame):
            c = next((x for x in source_rig.contacts if x.name == span.site), None)
            if c is not None:
                wanted[span.site] = source_pose[c.node].local_to_world(c.point)

        # 2 -- Root verschieben, Minimum ueber alle Kontakte
        shift = root_shift_for(target_rig, out, schedule, frame, wanted)
        shifts.append(shift)
        if shift:
            if not out.root_translation:
                out.root_translation = [(0.0, 0.0, 0.0)] * clip.frame_count
            i = min(frame, len(out.root_translation) - 1)
            x, y, z = out.root_translation[i]
            out.root_translation[i] = (x, y + shift, z)

        # 3 -- Ketten loesen, gruppiert nach Endbone
        for node, spans in _group_by_node(target_rig, schedule.engaged_at(frame)).items():
            targets = [wanted[s.site] for s in spans if s.site in wanted]
            sites = [s.site for s in spans if s.site in wanted]
            if targets:
                _solve_group(target_rig, out, frame, node, sites, targets)

    return RetargetResult(clip=out, root_shift=shifts)


def _group_by_node(rig: Rig, spans: list[Span]) -> dict[str, list[Span]]:
    """Bündelt Kontakte nach dem Bone, an dem sie haengen.

    Ferse und Zehe haengen am selben Fuss und werden von derselben Kette bewegt. Einzeln
    geloest ueberschreibt die zweite die erste, keine von beiden sitzt danach richtig,
    und die Fussstellung selbst wird nie angefasst -- der Fuss spiesst in den Boden oder
    schwebt darueber. Eine Gruppe je Bone ist die Einheit, die tatsaechlich loesbar ist:
    die Kette bringt sie hin, die Bone-Drehung legt sie flach.
    """
    out: dict[str, list[Span]] = {}
    by_name = {c.name: c for c in rig.contacts}
    for s in spans:
        if s.kind not in ("planted", "sliding"):
            continue
        c = by_name.get(s.site)
        if c is not None:
            out.setdefault(c.node, []).append(s)
    return out


def _centroid(points: list[quat.Vec3]) -> quat.Vec3:
    n = float(len(points))
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def _solve_group(
    rig: Rig,
    clip: Clip,
    frame: int,
    node: str,
    sites: list[str],
    targets: list[quat.Vec3],
) -> None:
    chain = chain_of(rig, node)
    if chain is None:
        return
    root_bone, mid_bone, end_bone = chain

    length_a = rig.by_name[mid_bone].rest_length
    length_b = rig.by_name[end_bone].rest_length
    if length_a < 1e-6 or length_b < 1e-6:
        return

    by_name = {c.name: c for c in rig.contacts}
    locals_ = [by_name[s].point for s in sites]
    clip.rotations.setdefault(root_bone, [quat.IDENTITY] * clip.frame_count)
    clip.rotations.setdefault(mid_bone, [quat.IDENTITY] * clip.frame_count)
    clip.rotations.setdefault(end_bone, [quat.IDENTITY] * clip.frame_count)

    target_centroid = _centroid(targets)

    # Zwei Durchgaenge: die Kette bringt die Gruppe hin, die Bone-Drehung legt sie flach,
    # und weil das Drehen den Schwerpunkt wieder verschiebt, wird die Kette einmal
    # nachgezogen. Danach bewegt sich nichts mehr nennenswert.
    for _ in range(2):
        pose = fk.solve(rig, clip, frame, include_root_translation=True)
        origin = pose[root_bone].position
        current = [pose[node].local_to_world(p) for p in locals_]
        offset = quat.sub(target_centroid, _centroid(current))
        goal = quat.add(pose[node].position, offset)

        to_goal = quat.sub(goal, origin)
        distance = quat.length(to_goal)
        if distance < 1e-6:
            return

        interior = solve_two_bone(length_a, length_b, distance)
        parent = rig.by_name[root_bone].parent
        parent_rot = pose[parent].rotation if parent else quat.IDENTITY
        goal_dir = quat.apply(
            quat.conjugate(parent_rot), quat.scale(to_goal, 1.0 / distance)
        )

        # Beugeebene. Ihre Normale muss senkrecht auf der Zielrichtung stehen, sonst
        # ist "um diese Achse aufbiegen" gar keine Bewegung in Richtung Ziel. Eine feste
        # Achse wie (1,0,0) taeuscht das nur, solange alle Gliedmassen in dieselbe
        # Richtung zeigen -- bei gespreizten Beinen kippt das Knie seitlich weg, und
        # links und rechts weichen spiegelbildlich voneinander ab.
        # Die Beugeachse liegt senkrecht auf der Ebene, die die Kette in Ruhe aufspannt.
        # Bei einer geraden Ruhelage -- Biped -- ist diese Ebene entartet; dann sagt das
        # Scharnier des Gelenks, worum gebeugt wird.
        a = rig.by_name[mid_bone].offset
        b = rig.by_name[end_bone].offset
        normal = _cross(a, b)
        normal = (
            _unit(normal)
            if quat.length(normal) > 1e-6
            else _orthogonal_to(_bend_axis(rig, mid_bone), _unit(a))
        )

        # Die Beugeebene hat zwei Loesungen -- das Knie kann nach vorn oder nach hinten
        # ausschlagen, beide erreichen das Ziel. Welche richtig ist, sagt das Gelenk
        # selbst: gespiegelte Gliedmassen tragen denselben Scharnierachse, aber
        # entgegengesetzte Grenzen (``[0, 120]`` links, ``[-120, 0]`` rechts). Ein fest
        # gewaehltes Vorzeichen loest daher die eine Seite und laesst die andere von der
        # Klemmung auf null ziehen -- sichtbar als Figur, die nur halb einknickt.
        # Beide durchrechnen und die zulaessige nehmen ist billig und braucht keine
        # Annahme darueber, wie das Rig seine Spiegelung schreibt.
        best = None
        for candidate in (normal, quat.scale(normal, -1.0)):
            root_rot, mid_rot = _chain_rotations(
                rig, mid_bone, end_bone, goal_dir, interior, candidate
            )
            penalty = _joint_violation(rig, mid_bone, mid_rot) + _joint_violation(
                rig, root_bone, root_rot
            )
            if best is None or penalty < best[0]:
                best = (penalty, root_rot, mid_rot)

        _, root_rot, mid_rot = best
        clip.rotations[root_bone][frame] = _clamp_to_joint(rig, root_bone, root_rot)
        clip.rotations[mid_bone][frame] = _clamp_to_joint(rig, mid_bone, mid_rot)

        if len(locals_) >= 2:
            _level_end_bone(rig, clip, frame, node, end_bone, locals_, targets)


def _level_end_bone(
    rig: Rig,
    clip: Clip,
    frame: int,
    node: str,
    end_bone: str,
    locals_: list[quat.Vec3],
    targets: list[quat.Vec3],
) -> None:
    """Dreht den Endbone so, dass seine Kontaktpunkte auf der Zielflaeche liegen.

    Der Sohlen-Schritt. Ohne ihn steht der Fuss im Winkel der Quellproportionen auf
    einem Boden, den ein anders gebautes Bein in einem anderen Winkel erreicht.
    """
    pose = fk.solve(rig, clip, frame, include_root_translation=True)
    current = [pose[node].local_to_world(p) for p in locals_]

    have = quat.sub(current[-1], current[0])
    want = quat.sub(targets[-1], targets[0])
    if quat.length(have) < 1e-6 or quat.length(want) < 1e-6:
        return

    correction = _rotation_between(_unit(have), _unit(want))
    parent = rig.by_name[end_bone].parent
    parent_rot = pose[parent].rotation if parent else quat.IDENTITY
    world_new = quat.mul(correction, pose[end_bone].rotation)
    local_new = quat.mul(quat.conjugate(parent_rot), world_new)
    clip.rotations[end_bone][frame] = _clamp_to_joint(
        rig, end_bone, quat.canonical(local_new)
    )


def _chain_rotations(
    rig: Rig,
    mid_bone: str,
    end_bone: str,
    goal_dir: quat.Vec3,
    interior: float,
    normal: quat.Vec3,
) -> tuple[quat.Quat, quat.Quat]:
    """Die beiden Rotationen einer Zwei-Knochen-Kette fuer eine gegebene Beugeebene.

    Erst die Mitte auf den Zielwinkel bringen, dann die ganze Kette so drehen, dass ihr
    Ende in Zielrichtung zeigt. Diese Reihenfolge macht die Ruhelage bedeutungslos: was
    die Wurzel drehen muss, wird aus der *bereits gebeugten* Kette abgelesen statt aus
    einer Annahme darueber, wie sie ruht.
    """
    a = rig.by_name[mid_bone].offset  # Wurzel -> Mitte, Ruhelage
    b = rig.by_name[end_bone].offset  # Mitte -> Ende, Ruhelage

    rest_interior = math.pi - _angle_between(a, b)
    mid_rot = quat.canonical(quat.from_axis_angle(normal, interior - rest_interior))

    # Wo das Ende nach dieser Beugung liegt, im Bezugssystem der Wurzel.
    reached = quat.add(a, quat.apply(mid_rot, b))
    root_rot = quat.canonical(_rotation_between(_unit(reached), goal_dir))
    return root_rot, mid_rot


def _joint_violation(rig: Rig, bone: str, rotation: quat.Quat) -> float:
    """Um wie viel Grad eine Rotation die Gelenkgrenzen verletzt. Null heisst zulaessig."""
    joint = rig.by_name[bone].joint
    if joint.type == "hinge" and joint.axis is not None and joint.range is not None:
        signed = _hinge_angle(rotation, joint.axis)
        lo, hi = joint.range
        return max(0.0, lo - signed, signed - hi)
    if joint.type == "ball" and joint.swing is not None:
        angle = 2.0 * math.degrees(
            math.atan2(
                math.sqrt(sum(rotation[i] ** 2 for i in range(3))), abs(rotation[3])
            )
        )
        return max(0.0, angle - joint.swing)
    return 0.0


def _hinge_angle(rotation: quat.Quat, axis: quat.Vec3) -> float:
    """Vorzeichenbehafteter Winkel einer Rotation um ``axis``, in Grad."""
    angle = 2.0 * math.atan2(
        math.sqrt(sum(rotation[i] ** 2 for i in range(3))), abs(rotation[3])
    )
    dot = sum(rotation[i] * axis[i] for i in range(3))
    if rotation[3] < 0:
        dot = -dot
    return math.degrees(angle) * (1.0 if dot >= 0 else -1.0)


def _orthogonal_to(hint: quat.Vec3, direction: quat.Vec3) -> quat.Vec3:
    """Einheitsvektor senkrecht zu ``direction``, so nah an ``hint`` wie moeglich.

    Gram-Schmidt. Der Hinweis kommt aus der aktuellen Beugerichtung des Gelenks, damit
    das Knie dort bleibt, wo es vorher war, statt in eine beliebige Loesung zu springen.
    """
    d = _unit(direction)
    dot = hint[0] * d[0] + hint[1] * d[1] + hint[2] * d[2]
    perp = quat.sub(hint, quat.scale(d, dot))
    if quat.length(perp) < 1e-6:
        fallback = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
        perp = _cross(d, fallback)
    return _unit(perp)


def _unit(v: quat.Vec3) -> quat.Vec3:
    n = quat.length(v)
    return quat.scale(v, 1.0 / n) if n > 1e-9 else (0.0, -1.0, 0.0)


def _bend_axis(rig: Rig, bone: str) -> quat.Vec3:
    """Achse, um die die Kette aufgeht.

    Bei einem Scharnier steht sie in der Rig-Datei -- das ist die richtige Antwort,
    denn ein Knie beugt genau um seine eigene Achse. Sonst quer zum Segment.
    """
    joint = rig.by_name[bone].joint
    if joint.type == "hinge" and joint.axis is not None:
        return _unit(joint.axis)
    return (1.0, 0.0, 0.0)


def _rotation_between(a: quat.Vec3, b: quat.Vec3) -> quat.Quat:
    """Kuerzeste Rotation, die ``a`` auf ``b`` dreht."""
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    if dot > 1.0 - 1e-9:
        return quat.IDENTITY
    if dot < -1.0 + 1e-9:
        # Gegenlaeufig: irgendeine Achse senkrecht zu a.
        axis = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
        perp = _unit(_cross(a, axis))
        return quat.canonical(quat.from_axis_angle(perp, math.pi))
    axis = _unit(_cross(a, b))
    return quat.canonical(quat.from_axis_angle(axis, math.acos(min(1.0, max(-1.0, dot)))))


def _cross(a: quat.Vec3, b: quat.Vec3) -> quat.Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
