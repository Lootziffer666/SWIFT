"""Conformance-Vektoren: JSON rein, JSON raus, sprachneutral.

Der Kern der Engine-Agnostik. Eine einzelne Implementierung beweist nichts -- ihre
stillschweigenden Annahmen sind vom Format nicht unterscheidbar. Erst wenn eine zweite,
unabhaengig geschriebene Implementierung dieselben Vektoren besteht, ist gezeigt, dass
das Verhalten in der Spec steht und nicht im Code.

**Gestuft nach Rolle.** Nicht jede Implementierung braucht alles: ein duenner
Engine-Adapter, der nur gebakene Daten abspielt, muss weder glTF lesen noch FK rechnen.
Die Stufen machen explizit, was fuer welche Rolle Pflicht ist.

**Exakt vs. toleriert.** Integer-Stufen werden bit-genau verglichen, Float-Stufen mit
angegebener Toleranz. Das ist keine Bequemlichkeit, sondern die Begruendung fuer den
gesamten Aufbau: weil Gleitkomma sprachuebergreifend nicht exakt reproduzierbar ist,
liegt der Gameplay-Pfad vollstaendig in den Integer-Stufen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from . import bake as bake_mod
from . import fixed, fk, gold, mirror, quat, sim
from .rig import Rig, load_builtin

VECTOR_DIR = Path(__file__).resolve().parents[2] / "conformance" / "vectors"

TIERS = {
    "fixed": "Fixed-Point-Arithmetik. Exakt. Pflicht fuer jede Rolle.",
    "fk": "Forward Kinematics. Toleriert. Pflicht fuer Renderer und Bake-Werkzeuge.",
    "mirror": "Spiegelung. Toleriert. Pflicht fuer Bake-Werkzeuge.",
    "bake": "Box-Bake in Fixed-Point. Exakt. Pflicht fuer Bake-Werkzeuge.",
    "sim": "Deterministische Simulation. Exakt. Pflicht fuer jede spielende Rolle.",
    "contact": "Kontaktplan und Retargeting. Gemischt. Pflicht fuer Bake-Werkzeuge.",
}

FLOAT_TOLERANCE = 1e-6


# --------------------------------------------------------------- erzeugen


def _vec_fixed() -> list[dict]:
    """Rundungsverhalten. Halbe Werte von Null weg, Boxen nach aussen."""
    u = fixed.UNIT_SCALE
    halves = [0.5, 1.5, 2.5, 3.5, -0.5, -1.5, -2.5]
    return [
        {
            "id": "fixed/half-away-from-zero",
            "tier": "fixed",
            "comparison": "exact",
            "note": (
                "Nicht Bankers Rounding. Pythons round() rundet halbe Werte zur "
                "naechsten geraden Zahl; in anderen Sprachen ist das nicht die "
                "Voreinstellung, und zwei konforme Implementierungen liefen auseinander."
            ),
            "input": {"unit_scale": u, "values": [h / u for h in halves]},
            "expected": {"fixed": [fixed.to_fixed(h / u) for h in halves]},
        },
        {
            "id": "fixed/box-rounds-outward",
            "tier": "fixed",
            "comparison": "exact",
            "note": "min abwaerts, max aufwaerts -- Rundung darf keinen Treffer verschlucken.",
            "input": {
                "unit_scale": u,
                "min": [0.1234, -0.5001, 0.0009],
                "max": [0.4321, 0.5001, 0.0011],
            },
            "expected": {
                "min": [fixed.floor_fixed(v) for v in (0.1234, -0.5001, 0.0009)],
                "max": [fixed.ceil_fixed(v) for v in (0.4321, 0.5001, 0.0011)],
            },
        },
    ]


def _clip_payload(clip) -> dict:
    """Clip als reines JSON -- damit die FK-Stufe keinen glTF-Parser voraussetzt."""
    return {
        "fps": clip.fps,
        "frame_count": clip.frame_count,
        "rotations": {
            bone: [list(quat.canonical(q)) for q in track]
            for bone, track in sorted(clip.rotations.items())
        },
        "root_translation": [list(t) for t in clip.root_translation],
    }


def _vec_fk(rig: Rig) -> list[dict]:
    out = []
    for rig_id in ("biped/1", "hexapod/1"):
        r = load_builtin(rig_id)
        clip = gold.build_clip(r) if rig_id == "biped/1" else _rest_clip(r)
        frames = []
        for f in range(clip.frame_count):
            pose = fk.solve(r, clip, f, include_root_translation=True)
            frames.append(
                {
                    bone: {
                        "position": list(pose[bone].position),
                        "rotation": list(pose[bone].rotation),
                    }
                    for bone in r.names
                }
            )
        out.append(
            {
                "id": f"fk/{rig_id.replace('/', '-')}",
                "tier": "fk",
                "comparison": "approx",
                "tolerance": FLOAT_TOLERANCE,
                "note": (
                    "Welttransforms je Frame. Ein einziger Vorwaertsdurchlauf genuegt, "
                    "weil Eltern in der Rig-Reihenfolge vor Kindern stehen."
                ),
                "input": {"rig": rig_id, "clip": _clip_payload(clip), "include_root_translation": True},
                "expected": {"frames": frames},
            }
        )

    r = load_builtin("biped/1")
    clip = gold.build_clip(r)
    out.append(
        {
            "id": "fk/bone-lengths-are-invariant",
            "tier": "fk",
            "comparison": "approx",
            "tolerance": 1e-9,
            "note": (
                "Die Kernaussage des Formats: Verkuerzung kann nur Rotation sein. "
                "Gemessene Segmentlaenge muss in jedem Frame der Rest-Laenge entsprechen."
            ),
            "input": {"rig": "biped/1", "clip": _clip_payload(clip)},
            "expected": {
                "lengths": {
                    b.name: b.rest_length for b in r if b.parent is not None
                }
            },
        }
    )
    return out


def _rest_clip(r: Rig):
    from .glb import Clip

    return Clip(name="rest", fps=30, frame_count=1, rig_id=r.id)


def _vec_mirror(rig: Rig) -> list[dict]:
    clip = gold.build_clip(rig)
    mirrored = mirror.mirror_clip(rig, clip)
    data = gold.build_combat(rig)
    m_data = mirror.mirror_combat(rig, data)
    return [
        {
            "id": "mirror/clip",
            "tier": "mirror",
            "comparison": "approx",
            "tolerance": FLOAT_TOLERANCE,
            "note": (
                "Kanaele ueber die Symmetrietabelle tauschen, dann (x,y,z,w) -> "
                "(x,-y,-z,w). Zweimal gespiegelt muss die Ausgangslage ergeben."
            ),
            "input": {"rig": rig.id, "clip": _clip_payload(clip)},
            "expected": {"clip": _clip_payload(mirrored)},
        },
        {
            "id": "mirror/boxes",
            "tier": "mirror",
            "comparison": "approx",
            "tolerance": FLOAT_TOLERANCE,
            "note": (
                "min.x' = -max.x, max.x' = -min.x. Wer x -> -x einzeln auf beide "
                "Grenzen anwendet, vertauscht sie und verschiebt die Box um ihre Breite."
            ),
            "input": {
                "rig": rig.id,
                "boxes": [
                    {"node": b.node, "min": list(b.min), "max": list(b.max)}
                    for f in data.frames
                    for b in f.hit + f.hurt
                ][:6],
            },
            "expected": {
                "boxes": [
                    {"node": b.node, "min": list(b.min), "max": list(b.max)}
                    for f in m_data.frames
                    for b in f.hit + f.hurt
                ][:6]
            },
        },
    ]


def _vec_bake(rig: Rig) -> list[dict]:
    clip = gold.build_clip(rig)
    data = gold.build_combat(rig)
    baked = bake_mod.bake(rig, clip, data)
    return [
        {
            "id": "bake/jab",
            "tier": "bake",
            "comparison": "exact",
            "note": (
                "Node-lokale Boxen -> Weltraum-AABB in Subunits. Alle acht Ecken werden "
                "transformiert, nicht nur min und max -- bei rotierten Boxen ergaebe "
                "das eine zu kleine Huelle."
            ),
            "input": {
                "rig": rig.id,
                "clip": _clip_payload(clip),
                "combat": data.to_dict(),
            },
            "expected": {"baked": baked},
        }
    ]


def _sim_scenarios() -> list[tuple[str, str, dict]]:
    A, B = sim.IN_ATTACK, sim.IN_BLOCK
    L, R = sim.IN_LEFT, sim.IN_RIGHT
    return [
        (
            "sim/jab-lands",
            "Nah beieinander muss der Jab treffen und Hitstun ausloesen.",
            {
                "a_x": -40,
                "b_x": 40,
                "log": [[A if i == 0 else 0, 0] for i in range(14)],
            },
        ),
        (
            "sim/block-absorbs",
            "Derselbe Jab gegen gehaltenen Block: kein Schaden, Blockstun statt Hitstun.",
            {
                "a_x": -40,
                "b_x": 40,
                "log": [[A if i == 0 else 0, B] for i in range(14)],
            },
        ),
        (
            "sim/pushbox-separates",
            (
                "Aufeinander zulaufende Kaempfer duerfen sich nicht durchdringen. "
                "Startabstand und Laufdauer sind so gewaehlt, dass die Pushbox "
                "tatsaechlich eingreift -- bei zu grossem Abstand pruefte der Vektor "
                "nur, dass zwei Figuren laufen koennen."
            ),
            {
                "a_x": -150,
                "b_x": 150,
                "log": [[R, L] for _ in range(40)],
            },
        ),
        (
            "sim/whiff-out-of-range",
            "Ausser Reichweite darf derselbe Move nichts ausloesen.",
            {
                "a_x": -600,
                "b_x": 600,
                "log": [[A if i % 10 == 0 else 0, 0] for i in range(30)],
            },
        ),
    ]


def _synthetic_move(hit_max_x: int) -> dict:
    """Ein Move mit exakt kontrollierten Weltkoordinaten.

    Der Gold-Clip taugt nicht, um den Grenzfall zu pinnen: seine Boxen entstehen aus
    FK und Rundung, ihre genauen Kanten sind nicht frei waehlbar. Hier ist alles von
    Hand gesetzt, damit "beruehrt sich exakt" auch wirklich exakt ist.
    """
    return {
        "schema": "fcd-baked/1",
        "unit_scale": fixed.UNIT_SCALE,
        "fps": 60,
        "frame_count": 3,
        "tags": ["attack"],
        "frames": [
            {"frame": 0, "hit": [], "hurt": []},
            {
                "frame": 1,
                "hit": [{"min": [0, 0, -10], "max": [hit_max_x, 100, 10], "id": "probe"}],
                "hurt": [],
            },
            {"frame": 2, "hit": [], "hurt": []},
        ],
        "on_hit": {"damage": 7, "hitstun": 5, "blockstun": 0, "pushback": [0, 0, 0]},
        "on_block": {"damage": 0, "hitstun": 0, "blockstun": 3, "pushback": [0, 0, 0]},
    }


def _vec_boundary() -> list[dict]:
    """Beruehrende Kanten zaehlen NICHT als Treffer.

    Halboffene Intervalle, also strikt ``<``. Ohne festgeschriebene Konvention waehlt
    eine Implementierung ``<`` und die naechste ``<=``, und beide halten sich fuer
    richtig -- bis ein Treffer in der einen landet und in der anderen nicht.

    Der Verteidiger steht ohne eigene Aktion da und traegt damit die Standard-Hurtbox
    (x in [-45, 45] relativ zu seiner Position). Bei Verteidiger x = 100 liegt deren
    linke Kante auf 55; eine Hitbox des Angreifers bei x = 0 mit max.x = 55 beruehrt
    sie exakt, mit max.x = 56 ueberlappt sie um eine Subunit.
    """
    out = []
    for label, hit_max_x, should_hit in (
        ("touching", 55, False),
        ("one-subunit-overlap", 56, True),
    ):
        move = _synthetic_move(hit_max_x)
        a = sim.Fighter("A", {"attack": move}, x=0, facing=1)
        b = sim.Fighter("B", {"attack": move}, x=100, facing=-1)
        s = sim.Sim(a, b)
        log = [[sim.IN_ATTACK, 0], [0, 0], [0, 0], [0, 0]]
        trace = []
        for ia, ib in log:
            s.step(ia, ib)
            trace.append(s.snapshot())

        landed = any(e.kind == "hit" for e in s.events)
        assert landed is should_hit, (
            f"Grenzfall {label!r}: erwartet hit={should_hit}, tatsaechlich {landed}"
        )

        out.append(
            {
                "id": f"sim/boundary-{label}",
                "tier": "sim",
                "comparison": "exact",
                "note": (
                    f"Hitbox-Kante bei {hit_max_x}, Hurtbox-Kante bei 55. "
                    f"Treffer erwartet: {should_hit}. Beruehrung allein reicht nicht -- "
                    "die Ueberlappung ist strikt."
                ),
                "input": {
                    "rules": {
                        "max_health": 100,
                        "walk_speed": 6,
                        "stage_min": -1536,
                        "stage_max": 1536,
                        "push_apart": 0,
                    },
                    "fighters": [
                        {"name": "A", "x": 0, "facing": 1},
                        {"name": "B", "x": 100, "facing": -1},
                    ],
                    "moves": {"attack": move},
                    "log": log,
                },
                "expected": {"trace": trace, "events": [e.to_dict() for e in s.events]},
            }
        )
    return out


def _vec_sim(rig: Rig) -> list[dict]:
    clip = gold.build_clip(rig)
    data = gold.build_combat(rig)
    baked = bake_mod.bake(rig, clip, data)

    out = _vec_boundary()
    for vid, note, sc in _sim_scenarios():
        a = sim.Fighter("A", {"attack": baked}, x=sc["a_x"], facing=1)
        b = sim.Fighter("B", {"attack": baked}, x=sc["b_x"], facing=-1)
        s = sim.Sim(a, b)
        trace = []
        for ia, ib in sc["log"]:
            s.step(ia, ib)
            trace.append(s.snapshot())

        out.append(
            {
                "id": vid,
                "tier": "sim",
                "comparison": "exact",
                "note": note,
                "input": {
                    "rules": {
                        "max_health": s.rules.max_health,
                        "walk_speed": s.rules.walk_speed,
                        "stage_min": s.rules.stage_min,
                        "stage_max": s.rules.stage_max,
                        "push_apart": s.rules.push_apart,
                    },
                    "fighters": [
                        {"name": "A", "x": sc["a_x"], "facing": 1},
                        {"name": "B", "x": sc["b_x"], "facing": -1},
                    ],
                    "moves": {"attack": baked},
                    "log": sc["log"],
                },
                "expected": {
                    "trace": trace,
                    "events": [e.to_dict() for e in s.events],
                },
            }
        )
    return out


def _rest_pose_clip(r: Rig, frames: int = 3):
    from .glb import Clip

    return Clip(
        name="rest",
        fps=30,
        frame_count=frames,
        rig_id=r.id,
        rotations={b.name: [quat.IDENTITY] * frames for b in r},
        root_translation=[(0.0, 0.0, 0.0)] * frames,
    )


def _vec_contact(rig: Rig) -> list[dict]:
    """Kontaktplan, Root-Verschiebung und Retargeting."""
    from . import contact as contact_mod
    from . import gold, retarget

    out: list[dict] = []

    # -- Intervallkonvention ------------------------------------------------
    out.append(
        {
            "id": "contact/spans-are-inclusive",
            "tier": "contact",
            "comparison": "exact",
            "note": (
                "'to' ist inklusiv. Eine Spanne [4, 4] ist genau ein Frame. Wer sie "
                "exklusiv liest, verliert je Spanne den letzten Frame -- am Absprung "
                "genau den, der die Bewegung traegt. Ohne festgeschriebene Konvention "
                "waehlt eine Implementierung das eine und die naechste das andere."
            ),
            "input": {
                "frame_count": 8,
                "spans": [
                    {"site": "heel_l", "kind": "planted", "from": 0, "to": 3},
                    {"site": "toe_l", "kind": "planted", "from": 4, "to": 4},
                ],
            },
            "expected": {
                "engaged_per_frame": [
                    ["heel_l"], ["heel_l"], ["heel_l"], ["heel_l"],
                    ["toe_l"], [], [], [],
                ],
                "frame_counts": {"heel_l": 4, "toe_l": 1},
            },
        }
    )

    # -- Herleitung ist reproduzierbar --------------------------------------
    clip = gold.build_clip(rig)
    schedule = contact_mod.derive(rig, clip)
    out.append(
        {
            "id": "contact/derive-is-deterministic",
            "tier": "contact",
            "comparison": "exact",
            "note": (
                "Derselbe Clip ergibt denselben Plan. Die Herleitung ist eine "
                "Heuristik; sie wird einmal gerechnet, eingecheckt und ist ab dann "
                "Wahrheit. Rechnet jede Implementierung sie neu und kommt anders "
                "heraus, uebertraegt das Retargeting eine andere Invariante."
            ),
            "input": {
                "rig": rig.id,
                "clip_name": clip.name,
                "clip": _clip_payload(clip),
                "ground_y": 0.0,
                "threshold": contact_mod.DEFAULT_GROUND_THRESHOLD,
            },
            "expected": schedule.to_dict(),
        }
    )

    # -- Root-Verschiebung ist das Minimum ----------------------------------
    stocky = load_builtin("biped/1-stocky")
    result = retarget.retarget(rig, clip, schedule, stocky)
    out.append(
        {
            "id": "contact/root-shift-is-minimum",
            "tier": "contact",
            "comparison": "approx",
            "tolerance": 1e-6,
            "note": (
                "Die Root verschiebt sich um das Minimum ueber alle eingerasteten "
                "Kontakte, nicht um den Mittelwert -- sonst bleibt der tiefste "
                "unerreichbar und sein Bein ueberstreckt. Vorzeichenbehaftet: ein "
                "langbeinigeres Ziel hebt den Koerper, statt ihn zu senken. Und die "
                "Reichweite geht mit ein, nicht nur die Hoehendifferenz."
            ),
            "input": {
                "source_rig": rig.id,
                "target_rig": stocky.id,
                "clip": _clip_payload(clip),
                "schedule": schedule.to_dict(),
                "want": "root_shift",
            },
            "expected": {"root_shift": result.root_shift},
        }
    )

    # -- Kontakte bleiben stehen --------------------------------------------
    for source_id, target_id, ground_y, name in (
        ("biped/1", "biped/1-stocky", 0.0, "contact/retarget-preserves-planted"),
        ("hexapod/1", "hexapod/1-tall", -0.17, "contact/retarget-hexapod"),
    ):
        src = load_builtin(source_id)
        dst = load_builtin(target_id)
        c = gold.build_clip(src) if source_id == "biped/1" else _rest_pose_clip(src)
        sched = contact_mod.derive(src, c, ground_y=ground_y)
        res = retarget.retarget(src, c, sched, dst)

        positions = []
        for frame in range(c.frame_count):
            pose = fk.solve(dst, res.clip, frame, include_root_translation=True)
            by = {x.name: x for x in dst.contacts}
            positions.append(
                {
                    s: list(pose[by[s].node].local_to_world(by[s].point))
                    for s in sorted(sched.sites())
                }
            )

        legs = len([x for x in src.contacts if x.kind == "ground"])
        out.append(
            {
                "id": name,
                "tier": "contact",
                "comparison": "approx",
                "tolerance": 1e-6,
                "note": (
                    f"Kontakte sind das Invariante, Gelenkwinkel das Verhandelbare. "
                    f"{legs} Bodenkontakte, {source_id} -> {target_id}."
                    + (
                        " Sechs Beine durch denselben Loeser: er findet Ketten ueber "
                        "die Hierarchie, nicht ueber Gliedmassennamen. Und die Ruhelage "
                        "dieser Kette ist bereits gebeugt -- ein Loeser, der von einer "
                        "geraden Ruhelage ausgeht, faellt genau hier auf."
                        if "hexapod" in source_id
                        else ""
                    )
                ),
                "input": {
                    "source_rig": src.id,
                    "target_rig": dst.id,
                    "clip": _clip_payload(c),
                    "schedule": sched.to_dict(),
                    "want": "contacts",
                },
                "expected": {"contacts": positions},
            }
        )

    return out


def generate(out_dir: str | Path | None = None) -> list[Path]:
    """Erzeugt alle Vektoren aus der Referenz-Implementierung."""
    out = Path(out_dir) if out_dir else VECTOR_DIR
    out.mkdir(parents=True, exist_ok=True)
    rig = load_builtin("biped/1")

    vectors = (
        _vec_fixed()
        + _vec_fk(rig)
        + _vec_mirror(rig)
        + _vec_bake(rig)
        + _vec_sim(rig)
        + _vec_contact(rig)
    )

    written = []
    for v in vectors:
        p = out / (v["id"].replace("/", "__") + ".json")
        p.write_text(json.dumps(v, indent=2, sort_keys=True) + "\n")
        written.append(p)
    return written


# ------------------------------------------------------------------ pruefen


def _approx_equal(a: Any, b: Any, tol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_approx_equal(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_approx_equal(a[k], b[k], tol) for k in a)
    return a == b


SOLVERS: dict[str, Callable[[dict], dict]] = {}


def solver(tier: str) -> Callable:
    def wrap(fn):
        SOLVERS[tier] = fn
        return fn

    return wrap


@solver("fixed")
def _solve_fixed(inp: dict) -> dict:
    if "values" in inp:
        return {"fixed": [fixed.to_fixed(v) for v in inp["values"]]}
    return {
        "min": [fixed.floor_fixed(v) for v in inp["min"]],
        "max": [fixed.ceil_fixed(v) for v in inp["max"]],
    }


def _clip_from_payload(payload: dict, rig_id: str):
    from .glb import Clip

    return Clip(
        name="vector",
        fps=payload["fps"],
        frame_count=payload["frame_count"],
        rig_id=rig_id,
        rotations={
            bone: [tuple(q) for q in track]
            for bone, track in payload["rotations"].items()
        },
        root_translation=[tuple(t) for t in payload.get("root_translation", [])],
    )


@solver("fk")
def _solve_fk(inp: dict) -> dict:
    r = load_builtin(inp["rig"])
    clip = _clip_from_payload(inp["clip"], r.id)
    if "include_root_translation" not in inp:
        return {"lengths": {b.name: b.rest_length for b in r if b.parent is not None}}
    frames = []
    for f in range(clip.frame_count):
        pose = fk.solve(r, clip, f, include_root_translation=inp["include_root_translation"])
        frames.append(
            {
                bone: {"position": list(pose[bone].position), "rotation": list(pose[bone].rotation)}
                for bone in r.names
            }
        )
    return {"frames": frames}


@solver("mirror")
def _solve_mirror(inp: dict) -> dict:
    r = load_builtin(inp["rig"])
    if "clip" in inp:
        return {"clip": _clip_payload(mirror.mirror_clip(r, _clip_from_payload(inp["clip"], r.id)))}
    from .combat import Box

    boxes = [
        mirror.mirror_box(r, Box(b["node"], tuple(b["min"]), tuple(b["max"])))
        for b in inp["boxes"]
    ]
    return {"boxes": [{"node": b.node, "min": list(b.min), "max": list(b.max)} for b in boxes]}


@solver("bake")
def _solve_bake(inp: dict) -> dict:
    from .combat import CombatData

    r = load_builtin(inp["rig"])
    clip = _clip_from_payload(inp["clip"], r.id)
    return {"baked": bake_mod.bake(r, clip, CombatData.from_dict(inp["combat"]))}


@solver("contact")
def _solve_contact(inp: dict) -> dict:
    from . import contact as contact_mod
    from . import retarget

    # Reine Intervallarithmetik -- kein Rig, kein Clip, kein Loeser noetig.
    if "spans" in inp:
        schedule = contact_mod.ContactSchedule.from_dict(
            {
                "schema": contact_mod.SCHEMA,
                "clip": "vector",
                "rig": "biped/1",
                "frame_count": inp["frame_count"],
                "spans": inp["spans"],
            }
        )
        return {
            "engaged_per_frame": [
                sorted(s.site for s in schedule.engaged_at(f))
                for f in range(schedule.frame_count)
            ],
            "frame_counts": {s.site: s.frame_count for s in schedule.spans},
        }

    if "ground_y" in inp:
        r = load_builtin(inp["rig"])
        clip = _clip_from_payload(inp["clip"], r.id)
        clip.name = inp["clip_name"]
        return contact_mod.derive(
            r, clip, ground_y=inp["ground_y"], threshold=inp["threshold"]
        ).to_dict()

    src = load_builtin(inp["source_rig"])
    dst = load_builtin(inp["target_rig"])
    clip = _clip_from_payload(inp["clip"], src.id)
    schedule = contact_mod.ContactSchedule.from_dict(inp["schedule"])
    result = retarget.retarget(src, clip, schedule, dst)

    if inp["want"] == "root_shift":
        return {"root_shift": result.root_shift}

    by = {x.name: x for x in dst.contacts}
    sites = sorted(schedule.sites())
    positions = []
    for frame in range(clip.frame_count):
        pose = fk.solve(dst, result.clip, frame, include_root_translation=True)
        positions.append(
            {s: list(pose[by[s].node].local_to_world(by[s].point)) for s in sites}
        )
    return {"contacts": positions}


@solver("sim")
def _solve_sim(inp: dict) -> dict:
    rules = sim.Ruleset(**inp["rules"])
    fighters = [
        sim.Fighter(f["name"], inp["moves"], x=f["x"], facing=f["facing"])
        for f in inp["fighters"]
    ]
    s = sim.Sim(fighters[0], fighters[1], rules)
    trace = []
    for ia, ib in inp["log"]:
        s.step(ia, ib)
        trace.append(s.snapshot())
    return {"trace": trace, "events": [e.to_dict() for e in s.events]}


def run(vector_dir: str | Path | None = None) -> tuple[int, int, list[str]]:
    """Prueft alle Vektoren gegen diese Implementierung.

    Gibt (bestanden, gesamt, Fehlermeldungen) zurueck.
    """
    d = Path(vector_dir) if vector_dir else VECTOR_DIR
    failures: list[str] = []
    passed = total = 0

    for path in sorted(d.glob("*.json")):
        v = json.loads(path.read_text())
        total += 1
        tier = v["tier"]
        if tier not in SOLVERS:
            failures.append(f"{v['id']}: keine Implementierung fuer Stufe {tier!r}")
            continue

        actual = SOLVERS[tier](v["input"])
        expected = v["expected"]

        if v.get("comparison") == "exact":
            ok = json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
        else:
            ok = _approx_equal(actual, expected, v.get("tolerance", FLOAT_TOLERANCE))

        if ok:
            passed += 1
        else:
            failures.append(f"{v['id']} ({tier}, {v.get('comparison')}) weicht ab")

    return passed, total, failures
