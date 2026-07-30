"""Kontaktplan eines Clips (``spar-contact/1``) -- Schicht L3.

Das Rig sagt, wo ein Koerper koppeln *kann* (``Rig.contacts``). Es sagt nicht, was in
einem bestimmten Clip tatsaechlich gekoppelt *ist*. Genau diese Luecke schliesst der
Kontaktplan: je Kontaktstelle die Frame-Spannen, in denen sie eingerastet ist, und
woran.

Warum das eine eigene Datei ist und keine Ableitung
---------------------------------------------------
``combat.derive_phases()`` ist bewusst eine **Ansicht**: Startup/Active/Recovery lassen
sich jederzeit aus der Eventspur neu berechnen, und sie zu speichern wuerde nur eine
zweite Wahrheit schaffen, die veralten kann.

Beim Kontaktplan ist es genau umgekehrt, und der Unterschied ist wichtig genug, ihn
hinzuschreiben: **er wird abgeleitet, dann eingecheckt, und ist ab dann die Wahrheit.**
Die Herleitung ist eine Heuristik -- "Fuss ist am Boden, wenn er nah genug dran ist" --
und eine Heuristik, die jede Implementierung fuer sich neu rechnet, laeuft auseinander.
Genau dieselbe Klasse Fehler wie ``<`` gegen ``<=`` beim Overlap-Test: beide Seiten
halten sich fuer richtig, bis ein Fuss in der einen Implementierung klebt und in der
anderen rutscht. Deshalb erzeugt :func:`derive` einen Vorschlag, und die Datei
entscheidet.

Retargeting haengt unmittelbar daran: Kontakte sind das Invariante, Gelenkwinkel das
Verhandelbare (siehe :mod:`spar.retarget`). Raet das Zielwerkzeug die Kontakte anders
als das Quellwerkzeug, uebertraegt es die falsche Invariante.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import fk
from .glb import Clip
from .rig import Rig

SCHEMA = "spar-contact/1"

KINDS = ("planted", "sliding", "pushing", "carried")
"""Kontaktarten nach L3.

``planted``  fixiert -- der Weltpunkt darf sich nicht bewegen. Fuss am Boden.
``sliding``  gleitend -- bleibt auf der Flaeche, darf sich darauf bewegen. Schlittern.
``pushing``  stossend -- traegt Kraft, aber nur auf Druck. Faust am Kopf des Gegners.
``carried``  tragend -- folgt einem Objekt statt der Welt. Hand an der Waffe.
"""


@dataclass(frozen=True)
class ContactTarget:
    """Woran eine Kontaktstelle koppelt."""

    type: str
    """``ground`` | ``prop`` | ``world``"""
    y: float = 0.0
    """Bodenhoehe bei ``ground``."""
    id: str | None = None
    """Objektkennung bei ``prop``."""

    @classmethod
    def from_dict(cls, d: dict | None) -> "ContactTarget":
        d = d or {"type": "ground"}
        return cls(type=d.get("type", "ground"), y=float(d.get("y", 0.0)), id=d.get("id"))

    def to_dict(self) -> dict:
        out: dict = {"type": self.type}
        if self.type == "ground":
            out["y"] = self.y
        if self.id is not None:
            out["id"] = self.id
        return out


@dataclass(frozen=True)
class Span:
    """Eine Kontaktstelle, eingerastet ueber einen Frame-Bereich.

    ``start`` und ``end`` sind **beide inklusiv**. Das ist festgeschrieben, nicht
    Geschmack: Frame-Indizes sind diskret, und eine Spanne ``[4, 4]`` muss einen
    einzelnen Frame bedeuten koennen. Wer ``end`` exklusiv liest, verliert bei jeder
    Spanne den letzten Frame -- am Absprung genau den, auf den es ankommt.
    Vektor-gepinnt durch ``contact/spans-are-inclusive``.
    """

    site: str
    kind: str
    start: int
    end: int
    target: ContactTarget = field(default_factory=ContactTarget)

    def covers(self, frame: int) -> bool:
        return self.start <= frame <= self.end

    @property
    def frame_count(self) -> int:
        return self.end - self.start + 1


@dataclass
class ContactSchedule:
    """Kontaktplan eines Clips."""

    clip: str
    rig_id: str
    frame_count: int
    spans: list[Span] = field(default_factory=list)

    # ------------------------------------------------------------- Zugriff

    def engaged_at(self, frame: int) -> list[Span]:
        return [s for s in self.spans if s.covers(frame)]

    def of_kind(self, kind: str) -> list[Span]:
        return [s for s in self.spans if s.kind == kind]

    def sites(self) -> list[str]:
        seen: list[str] = []
        for s in self.spans:
            if s.site not in seen:
                seen.append(s.site)
        return seen

    # ------------------------------------------------------------- laden

    @classmethod
    def load(cls, path: str | Path) -> "ContactSchedule":
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, data: dict) -> "ContactSchedule":
        if data.get("schema") != SCHEMA:
            raise ValueError(f"Erwartet schema {SCHEMA!r}, gefunden {data.get('schema')!r}")

        frame_count = int(data["frame_count"])
        spans = []
        for raw in data.get("spans", []):
            kind = raw.get("kind", "planted")
            if kind not in KINDS:
                raise ValueError(f"Unbekannte Kontaktart {kind!r}, erlaubt: {KINDS}")
            start, end = int(raw["from"]), int(raw["to"])
            if start > end:
                raise ValueError(f"Spanne [{start}, {end}] ist verdreht")
            if start < 0 or end >= frame_count:
                raise ValueError(
                    f"Spanne [{start}, {end}] liegt ausserhalb von 0..{frame_count - 1}"
                )
            spans.append(
                Span(
                    site=raw["site"],
                    kind=kind,
                    start=start,
                    end=end,
                    target=ContactTarget.from_dict(raw.get("target")),
                )
            )

        return cls(
            clip=data["clip"],
            rig_id=data.get("rig", "biped/1"),
            frame_count=frame_count,
            spans=spans,
        )

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "clip": self.clip,
            "rig": self.rig_id,
            "frame_count": self.frame_count,
            "spans": [
                {
                    "site": s.site,
                    "kind": s.kind,
                    "from": s.start,
                    "to": s.end,
                    "target": s.target.to_dict(),
                }
                for s in self.spans
            ],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path

    def validate(self, rig: Rig) -> None:
        known = {c.name for c in rig.contacts}
        for s in self.spans:
            if s.site not in known:
                raise ValueError(f"Kontaktstelle {s.site!r} gibt es in {rig.id} nicht")


# ------------------------------------------------------------------ herleiten


DEFAULT_GROUND_THRESHOLD = 0.005
"""Wie nah am Boden als 'am Boden' zaehlt, in Metern.

Fuenf Millimeter. Absolut, nicht relativ zur beobachteten Streuung -- ein Clip, in dem
sich nichts bewegt, darf nicht dazu fuehren, dass Quantisierungsrauschen als Kontakt
gilt. Dieselbe Lektion wie bei der Kalibrierung in ``core/procedural/surface.py``.
"""


def derive(
    rig: Rig,
    clip: Clip,
    ground_y: float = 0.0,
    threshold: float = DEFAULT_GROUND_THRESHOLD,
) -> ContactSchedule:
    """Schlaegt einen Kontaktplan aus der Bewegung vor.

    Wertet nur ``ground``-Stellen aus: ob ein Fuss den Boden beruehrt, steht in der
    Geometrie. Ob eine Hand eine Waffe haelt, steht dort **nicht** -- ``carried`` und
    ``pushing`` muessen autoriert werden, weil der Clip das Objekt gar nicht kennt.
    Sie hier zu raten hiesse, Daten zu erfinden.

    Das Ergebnis ist ein Vorschlag. Es gehoert eingecheckt und ueberprueft; ab dann ist
    die Datei die Wahrheit und diese Funktion nur noch der bequeme erste Entwurf.
    """
    contacts = rig.contacts_of_kind("ground")
    if not contacts:
        return ContactSchedule(clip.name, rig.id, clip.frame_count, [])

    grounded: dict[str, list[bool]] = {c.name: [] for c in contacts}
    for frame in range(clip.frame_count):
        pose = fk.solve(rig, clip, frame, include_root_translation=True)
        for c in contacts:
            world = pose[c.node].local_to_world(c.point)
            grounded[c.name].append(world[1] <= ground_y + threshold)

    spans: list[Span] = []
    target = ContactTarget(type="ground", y=ground_y)
    for site in [c.name for c in contacts]:
        flags = grounded[site]
        start: int | None = None
        for frame, on in enumerate(flags):
            if on and start is None:
                start = frame
            elif not on and start is not None:
                spans.append(Span(site, "planted", start, frame - 1, target))
                start = None
        if start is not None:
            spans.append(Span(site, "planted", start, clip.frame_count - 1, target))

    return ContactSchedule(clip.name, rig.id, clip.frame_count, spans)
