"""Fixed-Point-Umrechnung fuer den Gameplay-Pfad.

Alles, was eine Kampfentscheidung beeinflusst, ist ganzzahlig. Siehe
``spec/determinism.md``.
"""

from __future__ import annotations

import math

UNIT_SCALE = 256
"""Subunits pro Weltenheit. 1 Weltenheit = 1 Meter, Aufloesung ~3,9 mm."""


def to_fixed(v: float) -> int:
    """Rundet zur naechsten Ganzzahl, halbe Werte von Null weg.

    Nicht ``round()`` -- Python rundet halbe Werte zur naechsten geraden Zahl
    (Bankers Rounding). Das ist in anderen Sprachen nicht die Voreinstellung und
    wuerde zwei konforme Implementierungen auseinanderlaufen lassen.
    """
    scaled = v * UNIT_SCALE
    return int(math.trunc(scaled + math.copysign(0.5, scaled)))


def to_float(v: int) -> float:
    return v / UNIT_SCALE


def floor_fixed(v: float) -> int:
    """Fuer Box-Minima: rundet abwaerts, damit die Box nie schrumpft."""
    return int(math.floor(v * UNIT_SCALE))


def ceil_fixed(v: float) -> int:
    """Fuer Box-Maxima: rundet aufwaerts, damit die Box nie schrumpft."""
    return int(math.ceil(v * UNIT_SCALE))


def vec_to_fixed(v: tuple[float, float, float]) -> list[int]:
    return [to_fixed(c) for c in v]
