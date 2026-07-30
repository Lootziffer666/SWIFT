"""Tests der Referenz-Implementierung.

Laufen ohne SWIFTs Abhaengigkeiten -- kein mediapipe, kein Blender, kein PySide6. Das
belegt die Selbstenthaltung, die ``git subtree split -P spar`` spaeter voraussetzt.
"""

from __future__ import annotations

import math

import pytest

from spar import bake as bake_mod
from spar import cue, fixed, fk, gold, mirror, quat, sim
from spar.glb import Clip, GltfProfileError, read_clip, write_clip
from spar.rig import Rig, RigError, load_builtin


@pytest.fixture(scope="module")
def rig() -> Rig:
    return load_builtin("biped/1")


@pytest.fixture(scope="module")
def clip(rig: Rig) -> Clip:
    return gold.build_clip(rig)


# ------------------------------------------------------------------- L1 Rig


def test_builtin_rig_loads(rig: Rig):
    assert rig.id == "biped/1"
    assert len(rig) == 17
    assert rig.root == "Hips"


def test_parents_precede_children(rig: Rig):
    """Ohne diese Ordnung braeuchte FK mehrere Durchlaeufe oder Rekursion."""
    seen: set[str] = set()
    for bone in rig:
        if bone.parent is not None:
            assert bone.parent in seen, f"{bone.name} steht vor seinem Elternteil"
        seen.add(bone.name)


def test_hierarchy_order_independent_of_file_order():
    """Die Rig-Datei darf ihre Bones in beliebiger Reihenfolge auffuehren."""
    doc = {
        "schema": "spar-rig/1",
        "id": "reversed/1",
        "root": "A",
        "bones": [
            {"name": "C", "parent": "B", "offset": [0, -1, 0]},
            {"name": "B", "parent": "A", "offset": [0, -1, 0]},
            {"name": "A", "parent": None, "offset": [0, 0, 0]},
        ],
    }
    r = Rig.from_dict(doc)
    assert [b.name for b in r] == ["A", "B", "C"]


def test_rig_rejects_orphan():
    doc = {
        "schema": "spar-rig/1",
        "id": "broken/1",
        "root": "A",
        "bones": [
            {"name": "A", "parent": None, "offset": [0, 0, 0]},
            {"name": "X", "parent": "Ghost", "offset": [0, 1, 0]},
        ],
    }
    with pytest.raises(RigError):
        Rig.from_dict(doc)


def test_rig_rejects_one_sided_symmetry():
    doc = {
        "schema": "spar-rig/1",
        "id": "broken/2",
        "root": "A",
        "bones": [
            {"name": "A", "parent": None, "offset": [0, 0, 0]},
            {"name": "L", "parent": "A", "offset": [-1, 0, 0]},
            {"name": "R", "parent": "A", "offset": [1, 0, 0]},
        ],
        "symmetry": {"L": "R"},
    }
    # Wechselseitigkeit wird beim Laden ergaenzt, nicht als Fehler gewertet.
    r = Rig.from_dict(doc)
    assert r.mirror_of("R") == "L"


def test_second_rig_needs_no_code_change():
    """Der eigentliche Test von L1: nichtmenschliche Anatomie ohne Sonderweg."""
    hexa = load_builtin("hexapod/1")
    assert len(hexa) == 21
    assert len(hexa.end_effectors()) == 6
    assert hexa.root == "Thorax"
    assert not any(b.name.startswith("Arm") for b in hexa)


def test_hexapod_fk_runs(rig):
    hexa = load_builtin("hexapod/1")
    c = Clip(name="rest", fps=60, frame_count=1, rig_id=hexa.id)
    pose = fk.solve(hexa, c, 0)
    assert len(pose) == len(hexa)
    for bone in hexa:
        if bone.parent is None:
            continue
        assert fk.bone_length(hexa, pose, bone.name) == pytest.approx(
            bone.rest_length, abs=1e-9
        )


# ---------------------------------------------------------------- L2 Clip/FK


def test_glb_roundtrip(tmp_path, rig, clip):
    p = write_clip(tmp_path / "jab.glb", clip, rig)
    back = read_clip(p, rig)
    assert back.name == clip.name
    assert back.fps == clip.fps
    assert back.frame_count == clip.frame_count
    for bone, track in clip.rotations.items():
        for i, q in enumerate(track):
            for a, b in zip(quat.canonical(q), back.rotations[bone][i]):
                assert a == pytest.approx(b, abs=1e-6)


def test_glb_rejects_foreign_rig(tmp_path, rig, clip):
    """Ein Clip fuer biped/1 darf nicht stillschweigend als hexapod/1 gelesen werden."""
    p = write_clip(tmp_path / "jab.glb", clip, rig)
    with pytest.raises(GltfProfileError):
        read_clip(p, load_builtin("hexapod/1"))


def test_bone_lengths_constant(rig, clip):
    """Die Kernaussage des Formats: Verkuerzung kann nur Rotation sein."""
    for frame in range(clip.frame_count):
        pose = fk.solve(rig, clip, frame)
        for bone in rig:
            if bone.parent is None:
                continue
            assert fk.bone_length(rig, pose, bone.name) == pytest.approx(
                bone.rest_length, abs=1e-9
            )


# ------------------------------------------------------------------ Spiegeln


def test_double_mirror_is_identity(rig, clip):
    twice = mirror.mirror_clip(rig, mirror.mirror_clip(rig, clip))
    for bone, track in clip.rotations.items():
        for i, q in enumerate(track):
            for a, b in zip(quat.canonical(q), twice.rotations[bone][i]):
                assert a == pytest.approx(b, abs=1e-9)


def test_box_mirror_keeps_min_below_max(rig):
    from spar.combat import Box

    box = Box("Hand.R", (-0.05, -0.05, -0.05), (0.09, 0.05, 0.05))
    m = mirror.mirror_box(rig, box)
    assert m.node == "Hand.L"
    assert m.min[0] < m.max[0], "min.x = -max.x, sonst liegt die Box um ihre Breite daneben"
    assert m.min[0] == pytest.approx(-0.09)
    assert m.max[0] == pytest.approx(0.05)


# -------------------------------------------------------------- Fixed-Point


def test_half_rounds_away_from_zero():
    """Nicht Bankers Rounding -- sonst laufen Implementierungen auseinander."""
    assert fixed.to_fixed(0.5 / fixed.UNIT_SCALE) == 1
    assert fixed.to_fixed(1.5 / fixed.UNIT_SCALE) == 2
    assert fixed.to_fixed(2.5 / fixed.UNIT_SCALE) == 3
    assert fixed.to_fixed(-0.5 / fixed.UNIT_SCALE) == -1


def test_box_rounding_is_conservative():
    """Eine gebakene Box darf nie kleiner sein als die exakte."""
    v = 1.0 / fixed.UNIT_SCALE / 3.0
    assert fixed.floor_fixed(v) <= v * fixed.UNIT_SCALE
    assert fixed.ceil_fixed(v) >= v * fixed.UNIT_SCALE


# ---------------------------------------------------------------- Bake / L6


def test_bake_only_has_hitboxes_in_active_frames(rig, clip):
    data = gold.build_combat(rig)
    baked = bake_mod.bake(rig, clip, data)
    active = [f["frame"] for f in baked["frames"] if f["hit"]]
    assert active == [3, 4]
    assert all(f["hurt"] for f in baked["frames"]), "Hurtbox darf nie fehlen"


def test_bake_is_integer_only(rig, clip):
    data = gold.build_combat(rig)
    baked = bake_mod.bake(rig, clip, data)
    for f in baked["frames"]:
        for kind in ("hit", "hurt"):
            for box in f[kind]:
                assert all(isinstance(c, int) for c in box["min"] + box["max"])


def test_gold_clip_passes_cue(rig, clip):
    findings = cue.run_all(rig, clip)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, cue.summarize(findings)


def test_cue_catches_hinge_violation(rig, clip):
    """Der Ellbogen darf sich nicht in die falsche Richtung biegen."""
    import copy

    broken = copy.deepcopy(clip)
    broken.rotations["Forearm.R"] = [
        quat.from_euler_zyx(90.0, 0.0, 0.0)
    ] * clip.frame_count
    findings = cue.check_joint_limits(rig, broken)
    assert any(f.subject == "Forearm.R" for f in findings)


def test_swing_twist_decomposition():
    q = quat.from_axis_angle((0.0, 1.0, 0.0), math.radians(40.0))
    swing, twist = cue.swing_twist(q, (0.0, 1.0, 0.0))
    assert swing == pytest.approx(0.0, abs=1e-6)
    assert twist == pytest.approx(40.0, abs=1e-4)


# -------------------------------------------------------------------- L2 Sim


def _fighters(rig):
    clip = gold.build_clip(rig)
    data = gold.build_combat(rig)
    baked = bake_mod.bake(rig, clip, data)
    return (
        sim.Fighter("A", {"attack": baked}, x=-60, facing=1),
        sim.Fighter("B", {"attack": baked}, x=60, facing=-1),
    )


def _run(rig, log):
    a, b = _fighters(rig)
    s = sim.Sim(a, b)
    s.run(log)
    return s


def test_sim_is_deterministic(rig):
    log = [(sim.IN_ATTACK if i == 2 else 0, sim.IN_RIGHT if i < 4 else 0) for i in range(40)]
    first = _run(rig, log).snapshot()
    for _ in range(100):
        assert _run(rig, log).snapshot() == first


def test_sim_state_is_integer_only(rig):
    log = [(sim.IN_ATTACK if i % 12 == 0 else 0, sim.IN_LEFT) for i in range(30)]
    snap = _run(rig, log).snapshot()
    for side in ("a", "b"):
        for key in ("x", "facing", "health", "move_frame", "stun"):
            assert isinstance(snap[side][key], int), f"{side}.{key} ist kein int"


def test_attack_can_land(rig):
    """Nah beieinander muss ein Jab treffen -- sonst prueft der Rest nichts."""
    a, b = _fighters(rig)
    a.x, b.x = -40, 40
    s = sim.Sim(a, b)
    s.run([(sim.IN_ATTACK if i == 0 else 0, 0) for i in range(12)])
    assert any(e.kind == "hit" for e in s.events), [str(e.kind) for e in s.events]
    assert b.health < 100


def test_blocking_reduces_damage(rig):
    a, b = _fighters(rig)
    a.x, b.x = -40, 40
    s = sim.Sim(a, b)
    s.run([(sim.IN_ATTACK if i == 0 else 0, sim.IN_BLOCK) for i in range(12)])
    assert b.health == 100, "Block darf keinen Schaden durchlassen"
    assert any(e.kind == "block" for e in s.events)


def test_fighters_do_not_overlap(rig):
    a, b = _fighters(rig)
    s = sim.Sim(a, b)
    s.run([(sim.IN_RIGHT, sim.IN_LEFT)] * 60)
    assert abs(b.x - a.x) >= s.rules.push_apart
