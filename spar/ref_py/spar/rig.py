"""L1 -- Anatomiegraph: was ein Koerper *ist*.

Ein Rig ist eine Datendatei, kein Sonderfall im Code. ``biped/1`` ist das erste Exemplar,
nicht das Format. Sechsarmiger Daemon, Spinne, Zentaur, Drache, segmentierte Wirbelsaeule
und Schwanz sind weitere Dateien -- kein Sonderweg. Anthropozentrik verschwindet dadurch
nicht als Feature, sondern als Annahme.

Knoten sind Gelenke, Kanten sind Segmente. Pro Gelenk: Typ, Freiheitsgrade,
Bewegungsgrenzen, Lastfaehigkeit. Die Grenzen sind zugleich das, was den
Holzpuppen-Editor moeglich macht -- Gliedmassen lassen sich nur so verschieben, wie das
Gelenk es zulaesst.

Knochenlaengen sind unveraenderlich. Das ist die Kernaussage des Formats: perspektivische
Verkuerzung entsteht ausschliesslich durch Rotation. Ein Arm, der in der Projektion
kuerzer wird, ist rotiert -- er kann nicht kuerzer *sein*.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Literal

SCHEMA = "spar-rig/1"

Vec3 = tuple[float, float, float]
JointType = Literal["fixed", "hinge", "ball"]


class RigError(Exception):
    """Die Rig-Datei ist ungueltig."""


@dataclass(frozen=True)
class Joint:
    """Bewegungsfreiheit eines Gelenks.

    ``fixed``  -- kein Freiheitsgrad.
    ``hinge``  -- ein Freiheitsgrad um ``axis``, begrenzt durch ``range`` (Grad).
                  Ellbogen und Knie: sie biegen nur in eine Richtung, und genau das
                  soll der Editor auch nicht erlauben zu verletzen.
    ``ball``   -- drei Freiheitsgrade: Schwenk innerhalb eines Kegels mit halbem
                  Oeffnungswinkel ``swing`` plus Drehung um die eigene Achse in
                  ``twist``.
    """

    type: JointType = "ball"
    axis: Vec3 | None = None
    range: tuple[float, float] | None = None
    swing: float | None = None
    twist: tuple[float, float] | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "Joint":
        if not d:
            return cls(type="ball", swing=180.0, twist=(-180.0, 180.0))
        t = d.get("type", "ball")
        if t not in ("fixed", "hinge", "ball"):
            raise RigError(f"Unbekannter Gelenktyp {t!r}")
        if t == "hinge":
            if "axis" not in d or "range" not in d:
                raise RigError("hinge braucht 'axis' und 'range'")
            ax = tuple(float(c) for c in d["axis"])
            rng = (float(d["range"][0]), float(d["range"][1]))
            if rng[0] > rng[1]:
                raise RigError(f"hinge range {rng} ist verdreht")
            return cls(type="hinge", axis=ax, range=rng)  # type: ignore[arg-type]
        if t == "fixed":
            return cls(type="fixed")
        tw = d.get("twist", [-180.0, 180.0])
        return cls(
            type="ball",
            swing=float(d.get("swing", 180.0)),
            twist=(float(tw[0]), float(tw[1])),
        )

    @property
    def dof(self) -> int:
        return {"fixed": 0, "hinge": 1, "ball": 3}[self.type]


@dataclass(frozen=True)
class Bone:
    name: str
    parent: str | None
    offset: Vec3
    """Rest-Translation relativ zum Elternteil, in Metern. Wird nie animiert."""
    joint: Joint = field(default_factory=Joint)
    load_bearing: bool = False
    roles: tuple[str, ...] = ()

    @property
    def rest_length(self) -> float:
        """Laenge des Segments vom Elternteil zu diesem Bone."""
        x, y, z = self.offset
        return math.sqrt(x * x + y * y + z * z)


@dataclass(frozen=True)
class Contact:
    """Ein Punkt, an dem der Koerper an die Welt oder an ein Objekt koppeln kann."""

    name: str
    node: str
    point: Vec3
    kind: str  # "ground" | "grip" | "strike" | ...


class Rig:
    """Ein geladener Anatomiegraph."""

    def __init__(
        self,
        rig_id: str,
        name: str,
        root: str,
        bones: list[Bone],
        symmetry: dict[str, str],
        contacts: list[Contact],
        mass: dict[str, float],
        reference_height: float = 0.0,
    ) -> None:
        self.id = rig_id
        self.name = name
        self.root = root
        self.reference_height = reference_height
        """Nominelle Standhoehe in Metern. Massstab fuer Groessen, die sich auf den
        Koerper beziehen statt auf die Welt -- etwa wie weit Retargeting die Root
        absenken darf. Ohne sie waere so eine Grenze fuer einen 0.35 m hohen
        Sechsbeiner dieselbe wie fuer einen 1.7 m hohen Biped."""
        self.bones = _topological(bones, root)
        self.by_name = {b.name: b for b in self.bones}
        self.index = {b.name: i for i, b in enumerate(self.bones)}
        self.names = tuple(b.name for b in self.bones)
        self.symmetry = symmetry
        self.contacts = contacts
        self.mass = mass

    # ------------------------------------------------------------- Zugriff

    def __len__(self) -> int:
        return len(self.bones)

    def __iter__(self) -> Iterator[Bone]:
        """Bones in Hierarchie-Reihenfolge: Eltern immer vor Kindern.

        Damit genuegt fuer FK ein einziger Vorwaertsdurchlauf, unabhaengig davon, in
        welcher Reihenfolge die Rig-Datei die Bones auffuehrt.
        """
        return iter(self.bones)

    def children_of(self, name: str) -> list[str]:
        return [b.name for b in self.bones if b.parent == name]

    def mirror_of(self, name: str) -> str:
        """Symmetriepartner; der Bone selbst, wenn er auf der Mittelachse liegt."""
        return self.symmetry.get(name, name)

    def end_effectors(self) -> list[str]:
        return [b.name for b in self.bones if "end_effector" in b.roles]

    def load_bearing(self) -> list[str]:
        return [b.name for b in self.bones if b.load_bearing]

    def contacts_of_kind(self, kind: str) -> list[Contact]:
        return [c for c in self.contacts if c.kind == kind]

    def missing(self, names: set[str]) -> list[str]:
        """Welche Bones dieses Rigs fehlen in ``names``. Leer heisst konform."""
        return [n for n in self.names if n not in names]

    # -------------------------------------------------------------- Laden

    @classmethod
    def load(cls, path: str | Path) -> "Rig":
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Rig":
        if data.get("schema") != SCHEMA:
            raise RigError(f"Erwartet schema {SCHEMA!r}, gefunden {data.get('schema')!r}")

        raw_bones = data.get("bones") or []
        if not raw_bones:
            raise RigError("Rig ohne Bones")

        bones = [
            Bone(
                name=b["name"],
                parent=b.get("parent"),
                offset=(float(b["offset"][0]), float(b["offset"][1]), float(b["offset"][2])),
                joint=Joint.from_dict(b.get("joint")),
                load_bearing=bool(b.get("load_bearing", False)),
                roles=tuple(b.get("roles", ())),
            )
            for b in raw_bones
        ]

        # Symmetrie wird beidseitig aufgeloest, damit die Datei nur ein Paar je
        # Beziehung nennen muss.
        symmetry = dict(data.get("symmetry") or {})
        symmetry.update({v: k for k, v in list(symmetry.items())})

        contacts = [
            Contact(
                name=c["name"],
                node=c["node"],
                point=(float(c["point"][0]), float(c["point"][1]), float(c["point"][2])),
                kind=c.get("kind", "ground"),
            )
            for c in (data.get("contacts") or [])
        ]

        rig = cls(
            rig_id=data.get("id", "unnamed"),
            name=data.get("name", data.get("id", "unnamed")),
            root=data["root"],
            bones=bones,
            symmetry=symmetry,
            contacts=contacts,
            mass=dict(data.get("mass_distribution") or {}),
            reference_height=float(data.get("reference_height", 0.0)),
        )
        rig.validate()
        return rig

    def validate(self) -> None:
        """Prueft Wohlgeformtheit. Wirft bei der ersten Verletzung."""
        names = set(self.by_name)

        if self.root not in names:
            raise RigError(f"Root {self.root!r} kommt in den Bones nicht vor")

        roots = [b.name for b in self.bones if b.parent is None]
        if roots != [self.root]:
            raise RigError(f"Genau ein elternloser Bone erwartet, gefunden: {roots}")

        for b in self.bones:
            if b.parent is not None and b.parent not in names:
                raise RigError(f"Bone {b.name!r} verweist auf unbekanntes Elternteil {b.parent!r}")

        for a, b in self.symmetry.items():
            if a not in names:
                raise RigError(f"Symmetrie nennt unbekannten Bone {a!r}")
            if b not in names:
                raise RigError(f"Symmetrie nennt unbekannten Bone {b!r}")
            if self.symmetry.get(b) != a:
                raise RigError(f"Symmetrie ist nicht wechselseitig: {a!r} -> {b!r}")

        for c in self.contacts:
            if c.node not in names:
                raise RigError(f"Kontakt {c.name!r} haengt an unbekanntem Bone {c.node!r}")

        for name in self.mass:
            if name not in names:
                raise RigError(f"mass_distribution nennt unbekannten Bone {name!r}")


def _topological(bones: list[Bone], root: str) -> list[Bone]:
    """Sortiert Bones so, dass Eltern vor Kindern stehen.

    Damit darf die Rig-Datei ihre Bones in beliebiger Reihenfolge auffuehren, ohne dass
    FK oder Serialisierung stillschweigend falsch werden. Erkennt dabei Zyklen und
    unerreichbare Bones -- beides waere sonst ein Fehler, der erst viel spaeter als
    verbogene Pose auffaellt.
    """
    by_parent: dict[str | None, list[Bone]] = {}
    for b in bones:
        by_parent.setdefault(b.parent, []).append(b)

    ordered: list[Bone] = []
    stack = list(by_parent.get(None, []))
    if len(stack) != 1 or stack[0].name != root:
        # validate() meldet das ausfuehrlich; hier nur nicht in eine Endlosschleife laufen.
        stack = [b for b in bones if b.name == root] or stack

    seen: set[str] = set()
    while stack:
        bone = stack.pop(0)
        if bone.name in seen:
            raise RigError(f"Zyklus in der Hierarchie bei {bone.name!r}")
        seen.add(bone.name)
        ordered.append(bone)
        stack.extend(by_parent.get(bone.name, []))

    if len(ordered) != len(bones):
        orphans = sorted({b.name for b in bones} - seen)
        raise RigError(f"Bones nicht von der Wurzel erreichbar: {', '.join(orphans)}")

    return ordered


# ------------------------------------------------------------------ Registry

RIG_DIR = Path(__file__).resolve().parents[2] / "rigs"
_cache: dict[str, Rig] = {}


def load_builtin(rig_id: str = "biped/1") -> Rig:
    """Laedt ein mitgeliefertes Rig aus ``spar/rigs/``."""
    if rig_id in _cache:
        return _cache[rig_id]
    filename = rig_id.replace("/", "-") + ".json"
    path = RIG_DIR / filename
    if not path.exists():
        available = sorted(p.stem for p in RIG_DIR.glob("*.json"))
        raise RigError(f"Rig {rig_id!r} nicht gefunden. Verfuegbar: {', '.join(available)}")
    rig = Rig.load(path)
    _cache[rig_id] = rig
    return rig
