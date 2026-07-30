"""Kommandozeile der Referenz-Implementierung."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bake as bake_mod
from . import conformance as conf
from . import contact as contact_mod
from . import cue, gold, viewer
from . import retarget as retarget_mod
from .combat import CombatData, derive_phases
from .contact import ContactSchedule
from .glb import read_clip, write_clip
from .rig import Rig, RigError, load_builtin


def _rig(args) -> Rig:
    if getattr(args, "rig_file", None):
        return Rig.load(args.rig_file)
    return load_builtin(args.rig)


def cmd_rigs(args) -> int:
    from .rig import RIG_DIR

    for path in sorted(RIG_DIR.glob("*.json")):
        try:
            r = Rig.load(path)
        except RigError as e:
            print(f"  {path.name:22} UNGUELTIG: {e}")
            continue
        print(
            f"  {r.id:14} {len(r):3} Bones  {len(r.end_effectors())} Endeffektoren  "
            f"{len(r.contacts)} Kontakte  Root={r.root}"
        )
    return 0


def cmd_build_gold(args) -> int:
    rig = _rig(args)
    paths = gold.build(args.out, rig)
    for kind, p in paths.items():
        print(f"  {kind:7} {p}")
    return 0


def cmd_render(args) -> int:
    rig = _rig(args)
    clip = read_clip(args.clip, rig)
    baked = bake_mod.load(args.baked) if args.baked else None
    total = 0
    for name, axes in (("", ("x", "y")), ("_side", ("-z", "y"))):
        total += len(
            viewer.render_sequence(
                rig, clip, args.out, baked=baked, axes=axes, tag=name
            )
        )
    print(f"  {total} Bilder nach {args.out} (Front- und Seitenansicht)")
    return 0


def cmd_check(args) -> int:
    rig = _rig(args)
    clip = read_clip(args.clip, rig)
    schedule = ContactSchedule.load(args.contacts) if getattr(args, "contacts", None) else None
    findings = cue.run_all(rig, clip, schedule)
    print(cue.summarize(findings))
    return 1 if any(f.severity == "error" for f in findings) else 0


def cmd_contacts(args) -> int:
    rig = _rig(args)
    clip = read_clip(args.clip, rig)
    schedule = contact_mod.derive(rig, clip, ground_y=args.ground_y)
    if args.out:
        print(f"  {schedule.save(args.out)}")
    else:
        print(json.dumps(schedule.to_dict(), indent=2))
    print(
        f"  {len(schedule.spans)} Spannen ueber {len(schedule.sites())} Stellen -- "
        "Vorschlag. Pruefen, committen; ab dann ist die Datei die Wahrheit."
    )
    return 0


def cmd_retarget(args) -> int:
    source = _rig(args)
    target = load_builtin(args.to)
    clip = read_clip(args.clip, source)
    schedule = (
        ContactSchedule.load(args.contacts)
        if args.contacts
        else contact_mod.derive(source, clip, ground_y=args.ground_y)
    )
    result = retarget_mod.retarget(source, clip, schedule, target)

    findings = cue.run_all(target, result.clip, schedule)
    errors = [f for f in findings if f.severity == "error"]
    shift = result.root_shift
    print(f"  {source.id} -> {target.id}, {clip.frame_count} Frames")
    print(f"  Root-Verschiebung {min(shift):+.4f} .. {max(shift):+.4f} m")
    print(f"  {cue.summarize(findings)}")
    if args.out:
        write_clip(args.out, result.clip, target)
        print(f"  {args.out}")
    return 1 if errors else 0


def cmd_phases(args) -> int:
    data = CombatData.load(args.combat)
    phases = derive_phases(data)
    print(f"  Clip {data.clip} / {data.animation}, {data.frame_count} Frames")
    for name, frames in phases.items():
        print(f"  {name:9} {frames}")
    return 0


def cmd_validate(args) -> int:
    rig = _rig(args)
    try:
        clip = read_clip(args.clip, rig)
    except Exception as e:  # GltfProfileError und Formatfehler
        print(f"  UNGUELTIG: {e}")
        return 1
    print(f"  OK: {clip.name}, {clip.frame_count} Frames @ {clip.fps} fps, Rig {clip.rig_id}")
    return 0


def cmd_conformance(args) -> int:
    if args.generate:
        written = conf.generate()
        print(f"  {len(written)} Vektoren erzeugt")
        print("  Achtung: geaenderte Vektoren sind eine Verhaltensaenderung, kein Aufraeumen.")
        return 0
    passed, total, failures = conf.run()
    for m in failures:
        print(f"  FAIL {m}")
    print(f"  {passed}/{total} Vektoren bestanden")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="spar", description="SPAR Referenz-Implementierung")
    p.add_argument("--rig", default="biped/1", help="Rig-ID aus spar/rigs (default: biped/1)")
    p.add_argument("--rig-file", help="Pfad zu einer Rig-Datei; sticht --rig")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("rigs", help="Mitgelieferte Rigs auflisten").set_defaults(fn=cmd_rigs)

    g = sub.add_parser("build-gold", help="Gold-Clip erzeugen (glb + combat + bake)")
    g.add_argument("-o", "--out", default="build")
    g.set_defaults(fn=cmd_build_gold)

    r = sub.add_parser("render", help="Clip headless zu PNG rendern")
    r.add_argument("clip")
    r.add_argument("--baked", help="fcd-baked/1, um Hitboxen einzuzeichnen")
    r.add_argument("-o", "--out", default="build/frames")
    r.set_defaults(fn=cmd_render)

    ct = sub.add_parser("contacts", help="Kontaktplan aus einem Clip vorschlagen")
    ct.add_argument("clip")
    ct.add_argument("-o", "--out", help="Zieldatei; ohne sie nach stdout")
    ct.add_argument("--ground-y", type=float, default=0.0, dest="ground_y")
    ct.set_defaults(fn=cmd_contacts)

    rt = sub.add_parser("retarget", help="Clip auf ein anderes Rig uebertragen")
    rt.add_argument("clip")
    rt.add_argument("--to", required=True, help="Ziel-Rig-ID, z.B. biped/1-stocky")
    rt.add_argument("--contacts", help="Kontaktplan; ohne ihn wird einer hergeleitet")
    rt.add_argument("--ground-y", type=float, default=0.0, dest="ground_y")
    rt.add_argument("-o", "--out", help="Ziel-.glb")
    rt.set_defaults(fn=cmd_retarget)

    c = sub.add_parser("check", help="CUE-Pruefungen auf einem Clip")
    c.add_argument("--contacts", help="Kontaktplan; macht aus dem Raten eine Aussage")
    c.add_argument("clip")
    c.set_defaults(fn=cmd_check)

    v = sub.add_parser("validate", help="glTF-Profil pruefen")
    v.add_argument("clip")
    v.set_defaults(fn=cmd_validate)

    ph = sub.add_parser("phases", help="Startup/Active/Recovery ableiten")
    ph.add_argument("combat")
    ph.set_defaults(fn=cmd_phases)

    cf = sub.add_parser("conformance", help="Conformance-Vektoren pruefen oder erzeugen")
    cf.add_argument("--generate", action="store_true", help="Vektoren neu erzeugen")
    cf.set_defaults(fn=cmd_conformance)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
