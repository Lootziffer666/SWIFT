"""Tests der Conformance-Suite selbst.

Eine Suite, die eine Verbiegung nicht bemerkt, ist Dekoration. Diese Tests pruefen
deshalb nicht nur, dass die Vektoren bestehen, sondern auch, dass sie ueberhaupt
anschlagen -- und zwar auf jede der Konventionen, die ``RUNNER.md`` festschreibt.
"""

from __future__ import annotations

import json

import pytest

from spar import conformance, fixed, fk, quat, sim


@pytest.fixture
def restore():
    """Setzt gepatchte Attribute nach dem Test zuverlaessig zurueck."""
    saved: list[tuple] = []

    def patch(obj, name, value):
        saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    yield patch
    for obj, name, value in reversed(saved):
        setattr(obj, name, value)


def test_vectors_are_committed():
    """Die Vektoren liegen im Repository, nicht nur im Generator."""
    files = list(conformance.VECTOR_DIR.glob("*.json"))
    assert files, f"keine Vektoren in {conformance.VECTOR_DIR}"
    assert len(files) >= 14


def test_all_vectors_pass():
    passed, total, failures = conformance.run()
    assert not failures, "\n".join(failures)
    assert passed == total


def test_every_tier_is_covered():
    tiers = set()
    for p in conformance.VECTOR_DIR.glob("*.json"):
        tiers.add(json.loads(p.read_text())["tier"])
    assert tiers == set(conformance.TIERS), (
        f"Stufen ohne Vektor: {set(conformance.TIERS) - tiers}"
    )


def test_vectors_declare_comparison_and_note():
    for p in conformance.VECTOR_DIR.glob("*.json"):
        v = json.loads(p.read_text())
        assert v.get("comparison") in ("exact", "approx"), v["id"]
        assert v.get("note"), f"{v['id']} sagt nicht, wofuer es da ist"
        if v["comparison"] == "approx":
            assert "tolerance" in v, f"{v['id']} ist toleriert, nennt aber keine Toleranz"


# ------------------------------------------------- schlaegt die Suite an?


def test_detects_touching_boxes_counted_as_hit(restore):
    """Beruehrende Kanten duerfen nicht treffen -- ``<``, nicht ``<=``."""
    restore(
        sim,
        "_overlaps",
        lambda a, b: (
            a[0] <= b[3] and b[0] <= a[3]
            and a[1] <= b[4] and b[1] <= a[4]
            and a[2] <= b[5] and b[2] <= a[5]
        ),
    )
    _, _, failures = conformance.run()
    assert any("boundary-touching" in f for f in failures)


def test_detects_broken_facing_mirror(restore):
    """Bei facing = -1 muessen min und max getauscht werden, nicht nur negiert."""

    def bad(box, x, facing):
        lo, hi = box["min"], box["max"]
        x0, x1 = (lo[0], hi[0]) if facing >= 0 else (-lo[0], -hi[0])
        return (x + x0, lo[1], lo[2], x + x1, hi[1], hi[2])

    restore(sim, "_to_world", bad)
    _, _, failures = conformance.run()
    assert failures


def test_detects_broken_fk_chaining(restore):
    """Die Elternrotation muss sich auf das Kind fortpflanzen."""
    restore(fk.quat, "mul", lambda a, b: b)
    _, _, failures = conformance.run()
    assert any("fk/" in f for f in failures)


def test_detects_bankers_rounding(restore):
    restore(fixed, "to_fixed", lambda v: int(round(v * fixed.UNIT_SCALE)))
    _, _, failures = conformance.run()
    assert any("half-away-from-zero" in f for f in failures)


def test_detects_boxes_rounded_inward(restore):
    """Boxen muessen nach aussen runden, sonst verschluckt Rundung Treffer."""
    restore(fixed, "ceil_fixed", lambda v: int(v * fixed.UNIT_SCALE))
    _, _, failures = conformance.run()
    assert any("box-rounds-outward" in f for f in failures)


# ------------------------------------------------------- Szenario-Gehalt


def _vector(name: str) -> dict:
    return json.loads((conformance.VECTOR_DIR / name).read_text())


def test_jab_scenario_actually_lands():
    v = _vector("sim__jab-lands.json")
    assert any(e["kind"] == "hit" for e in v["expected"]["events"])
    assert v["expected"]["trace"][-1]["b"]["health"] < 100


def test_block_scenario_takes_no_damage():
    v = _vector("sim__block-absorbs.json")
    assert any(e["kind"] == "block" for e in v["expected"]["events"])
    assert not any(e["kind"] == "hit" for e in v["expected"]["events"])
    assert v["expected"]["trace"][-1]["b"]["health"] == 100


def test_pushbox_scenario_actually_engages():
    """Ohne echten Kontakt pruefte der Vektor nur, dass zwei Figuren laufen koennen."""
    v = _vector("sim__pushbox-separates.json")
    trace = v["expected"]["trace"]
    gaps = [t["b"]["x"] - t["a"]["x"] for t in trace]
    limit = v["input"]["rules"]["push_apart"]
    assert min(gaps) == limit, f"Pushbox greift nie ein: kleinster Abstand {min(gaps)}"
    assert gaps[0] > limit, "Sie starten schon im Kontakt -- der Verlauf zeigt nichts"


def test_whiff_scenario_starts_moves_but_never_hits():
    v = _vector("sim__whiff-out-of-range.json")
    kinds = {e["kind"] for e in v["expected"]["events"]}
    assert "move_start" in kinds
    assert "hit" not in kinds


def test_boundary_pair_differs_by_one_subunit():
    touch = _vector("sim__boundary-touching.json")
    over = _vector("sim__boundary-one-subunit-overlap.json")
    tx = touch["input"]["moves"]["attack"]["frames"][1]["hit"][0]["max"][0]
    ox = over["input"]["moves"]["attack"]["frames"][1]["hit"][0]["max"][0]
    assert ox - tx == 1, "Das Paar muss sich um genau eine Subunit unterscheiden"
    assert not any(e["kind"] == "hit" for e in touch["expected"]["events"])
    assert any(e["kind"] == "hit" for e in over["expected"]["events"])
